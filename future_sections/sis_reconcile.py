"""Course Information requests vs. imported SIS sections (#7).

Two read-only questions, both answered live from the database so they are
current after every SIS import (nothing is stored or written):

* ``reconcile(academic_year)`` — per high school, course and term, how many
  sections the school asked for in Course Information against how many the
  SIS import created, flagged "Need N more" / "Remove N".
* ``candidate_sections(future_course)`` — the imported ``ClassSection``\\ s
  that could fulfil one request, with the ones that match on term and
  teacher marked as suggestions. Staff confirm the link
  (``FutureCourse.sis_sections``); the matcher never links on its own.

Matching key: high school, course and the request's academic year, then the
term. Section numbers are not used — tenants reassign them every year.

Terms are compared at the top level: a section imported into a sub-term
(e.g. fall ``3L``) counts against its parent term, so a school that asked for
"Fall" matches it. A tenant whose cis has no ``Term.parent`` compares terms
as they are.

A **Full year** request is counted against the request's own term unless
the tenant sets ``sis_full_year_term_code``: then it counts against the
top-level term holding a term whose code ends with that value (RVC places
year-long sections in the spring ``6L`` sub-term).
"""
from collections import Counter

from django.db.models import Q

CANCELLED_STATUSES = ('c', 'cancelled')


def _truthy(value):
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in ('1', 'true', 'on', 'yes', 'y')


def requested_count(section):
    """Sections one Course Information row asks for.

    ``number_of_sections`` when the tenant collects it and it is a number,
    otherwise 1 (a row is one section).
    """
    raw = (section or {}).get('number_of_sections')
    if raw in (None, ''):
        return 1
    try:
        return max(int(str(raw).strip()), 0)
    except (TypeError, ValueError):
        return 1


def _term_has_parent():
    from cis.models.term import Term
    return any(f.name == 'parent' for f in Term._meta.get_fields())


class TermBuckets:
    """Maps a term id to the top-level term it is compared under."""

    def __init__(self, academic_year, full_year_code=''):
        from cis.models.term import Term

        self.has_parent = _term_has_parent()
        terms = Term.objects.filter(academic_year=academic_year)
        self.terms = {str(t.id): t for t in terms}
        self.full_year_bucket = None
        code = (full_year_code or '').strip().lower()
        if code:
            matches = sorted(
                (t for t in self.terms.values()
                 if (t.code or '').strip().lower().endswith(code)),
                key=lambda t: t.code or '')
            if matches:
                self.full_year_bucket = self.top(str(matches[0].id))

    def top(self, term_id):
        """The top-level term id for ``term_id`` (itself without parents)."""
        term_id = str(term_id) if term_id else None
        if not term_id or not self.has_parent:
            return term_id
        seen = set()
        current = self.terms.get(term_id)
        while current is not None and current.parent_id \
                and str(current.parent_id) in self.terms \
                and current.id not in seen:
            seen.add(current.id)
            current = self.terms[str(current.parent_id)]
        return str(current.id) if current is not None else term_id

    def for_row(self, section):
        if self.full_year_bucket and _truthy((section or {}).get('full_year')):
            return self.full_year_bucket
        return self.top((section or {}).get('term'))

    def label(self, bucket):
        term = self.terms.get(bucket) if bucket else None
        return term.label if term is not None else 'No term'


def _full_year_code(academic_year=None):
    """The ``sis_full_year_term_code`` setting of the year's campus (review
    I3): ``cis_future_sections`` is a per-campus setting, so it is read in
    the record's campus context, not the serving one."""
    from .campus import record_context
    from .utils import get_fs_config
    with record_context(academic_year):
        return (get_fs_config() or {}).get('sis_full_year_term_code') or ''


def requested_by_bucket(future_course, buckets):
    """``Counter({bucket: n})`` for one request; empty unless teaching."""
    info = future_course.section_info or {}
    counts = Counter()
    if info.get('teaching') != 'yes':
        return counts
    for section in info.get('sections') or []:
        counts[buckets.for_row(section)] += requested_count(section)
    return counts


def imported_sections(academic_year):
    """Imported, non-cancelled ``ClassSection``\\ s for the academic year."""
    from cis.models.section import ClassSection

    cancelled = Q()
    for status in CANCELLED_STATUSES:
        cancelled |= Q(status__iexact=status)
    return ClassSection.objects.filter(
        term__academic_year=academic_year).exclude(cancelled)


def _flag(requested, imported):
    diff = imported - requested
    if diff < 0:
        return f'Need {-diff} more'
    if diff > 0:
        return f'Remove {diff}'
    return 'OK'


def reconcile(academic_year, highschool=None, flagged_only=False):
    """Requested vs. imported sections, one row per school, course and term.

    Covers every (school, course) pair that has a Course Information request
    for the year — a "not teaching" answer asks for 0, so sections the
    rollover created anyway are flagged "Remove N". Pairs nobody answered
    for are left out: there is nothing to compare.

    Returns a list of dicts: ``highschool``, ``course``, ``term``,
    ``requested``, ``imported``, ``linked``, ``difference``, ``flag``.
    """
    from .models import FutureCourse

    buckets = TermBuckets(academic_year, _full_year_code(academic_year))

    requests = FutureCourse.objects.filter(
        academic_year=academic_year).select_related(
        'teacher_course__course',
        'teacher_course__teacher_highschool__highschool')
    if highschool is not None:
        requests = requests.filter(
            teacher_course__teacher_highschool__highschool=highschool)

    requested = Counter()
    pairs = {}
    for fc in requests:
        cert = fc.teacher_course
        hs = cert.teacher_highschool.highschool
        key = (hs.id, cert.course_id)
        pairs[key] = (hs, cert.course)
        for bucket, n in requested_by_bucket(fc, buckets).items():
            requested[key + (bucket,)] += n

    imported = Counter()
    linked = Counter()
    if pairs:
        sections = imported_sections(academic_year).filter(
            highschool_id__in={k[0] for k in pairs},
            course_id__in={k[1] for k in pairs},
        )
        through = FutureCourse.sis_sections.through
        linked_ids = set(through.objects.filter(
            classsection_id__in=sections.values('id'),
        ).values_list('classsection_id', flat=True))
        for sec_id, hs_id, course_id, term_id in sections.values_list(
                'id', 'highschool_id', 'course_id', 'term_id'):
            if (hs_id, course_id) not in pairs:
                continue
            key = (hs_id, course_id, buckets.top(term_id))
            imported[key] += 1
            if sec_id in linked_ids:
                linked[key] += 1

    rows = []
    for key in set(requested) | set(imported):
        hs, course = pairs[key[:2]]
        req, imp = requested[key], imported[key]
        flag = _flag(req, imp)
        if flagged_only and flag == 'OK':
            continue
        rows.append({
            'highschool': hs,
            'course': course,
            'term': buckets.label(key[2]),
            'requested': req,
            'imported': imp,
            'linked': linked[key],
            'difference': imp - req,
            'flag': flag,
        })
    rows.sort(key=lambda r: (r['highschool'].name or '', str(r['course']),
                             r['term']))
    return rows


def candidate_sections(future_course):
    """Imported sections that could fulfil ``future_course``.

    Same high school, course and academic year, not cancelled, and not
    already linked to a different request. Returns
    ``(queryset, suggested_ids)``: a section is suggested when its term
    matches a requested term and its teacher is the request's teacher.
    """
    from .models import FutureCourse

    cert = future_course.teacher_course
    ths = cert.teacher_highschool
    taken = FutureCourse.sis_sections.through.objects.filter(
        futurecourse__academic_year=future_course.academic_year,
    ).exclude(futurecourse_id=future_course.pk).values('classsection_id')

    qs = imported_sections(future_course.academic_year).filter(
        highschool_id=ths.highschool_id, course_id=cert.course_id,
    ).exclude(id__in=taken).select_related('term', 'teacher__user').order_by(
        'term__code', 'section_number')

    buckets = TermBuckets(future_course.academic_year,
                          _full_year_code(future_course.academic_year))
    wanted = requested_by_bucket(future_course, buckets)
    suggested = {
        sec.id for sec in qs
        if wanted.get(buckets.top(sec.term_id))
        and sec.teacher_id == ths.teacher_id
    }
    return qs, suggested


def link_sections(future_course, sections, user):
    """Confirm ``sections`` as the request's SIS sections and log it."""
    from .utils import add_history_entry

    before = set(future_course.sis_sections.values_list('id', flat=True))
    after = {s.id for s in sections}
    if before == after:
        return False
    future_course.sis_sections.set(sections)
    labels = ', '.join(sorted(
        f'{s.term.label if s.term_id else ""} {s.class_number or s.section_number}'.strip()
        for s in sections)) or 'none'
    add_history_entry(future_course, user, f'Linked SIS sections: {labels}')
    future_course.save(update_fields=['meta'])
    return True

