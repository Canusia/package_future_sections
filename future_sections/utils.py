"""
Utility functions for the future_sections app.

Shared by both instructor and highschool_admin views.
"""

import datetime
import re

from django.shortcuts import get_object_or_404
from django.utils.html import strip_tags

from rest_framework.exceptions import PermissionDenied

from .models import FutureCourse, FutureProjection
from .schemas import TeachingSectionFieldSchema
from cis.models.highschool import HighSchool
from cis.models.highschool_administrator import HSAdministrator
from cis.models.teacher import Teacher, TeacherCourseCertificate
from cis.models.term import AcademicYear
from cis.utils import user_has_highschool_admin_role, user_has_instructor_role


_ANGLE = re.compile(r'[<>]')


def sanitize_plain_text(value):
    """Strip all HTML markup and residual angle brackets from free-text input.

    Dependency-free (no bleach/nh3): Django's ``strip_tags`` removes tags, and
    the ``_ANGLE`` scrub removes any ``<``/``>`` that ``strip_tags`` leaves on
    malformed input (``strip_tags`` is explicitly documented as not
    security-grade). Used to neutralise stored-XSS vectors (PT-24/PT-27) on
    name fields before they are persisted. Non-strings pass through unchanged.
    """
    if not isinstance(value, str):
        return value
    return _ANGLE.sub('', strip_tags(value)).strip()


def get_fs_config():
    """
    Get future sections configuration from database.

    Returns:
        dict: Configuration settings for future sections
    """
    from .settings.future_sections import future_sections as fs_settings
    return fs_settings.from_db()


def addable_courses_for_user(request, academic_year, course_type=None, campus=None):
    """Course queryset selectable in the add-teacher form.

    Mirrors ``AddNewTeacherForm.__init__``: HS admins get all active courses;
    instructors get only the courses they are certified for. When ``campus`` is
    given the list is narrowed to that campus. Shared by the form (initial
    render / bound validation) and the ``add-teacher-courses`` AJAX action so
    the two never drift.

    ``course_type`` is accepted for forward-compatibility but, matching current
    behavior, is not used to filter the list.
    """
    from cis.models.course import Course
    from cis.utils import user_has_highschool_admin_role, user_has_instructor_role

    qs = Course.objects.filter(status__iexact='active')
    if campus is not None:
        qs = qs.filter(campus=campus)

    # HS admins see everything active; only instructors are cert-scoped. The
    # HS-admin check wins when a user happens to hold both roles (as in the form).
    if (not user_has_highschool_admin_role(request.user)
            and user_has_instructor_role(request.user)):
        teacher_user = Teacher.objects.get(user__id=request.user.id)
        fs_config = get_fs_config()
        certified_course_ids = TeacherCourseCertificate.objects.filter(
            teacher_highschool__teacher=teacher_user,
            status__in=fs_config.get('teacher_course_status', []),
        ).values_list('course__id', flat=True)
        qs = qs.filter(id__in=certified_course_ids)

    return qs.distinct('title').order_by('title')


def render_course_display(template, course):
    """Expand the ``course_display_template`` placeholders for a Course.

    Supported placeholders: ``{course_name}``, ``{course_title}``,
    ``{credit_hours}``, ``{campus_name}``, ``{campus_code}``. The ``campus`` FK
    on Course is optional, so campus placeholders resolve to '' when unset.

    Falls back to ``course.title`` if the template references an unknown
    placeholder or is otherwise malformed. Single source of truth shared by the
    request-table serializers and viewsets so new placeholders land in one place.
    """
    campus = getattr(course, 'campus', None)
    try:
        return template.format(
            course_name=course.name or '',
            course_title=course.title,
            credit_hours=course.credit_hours,
            campus_name=(campus.name if campus else ''),
            campus_code=(campus.code if campus else ''),
        )
    except (KeyError, IndexError, ValueError):
        return course.title


def prev_year_status_filter(statuses):
    """Return the ``ClassSection`` status filter for *statuses*.

    *statuses* is the tenant's ``prev_year_class_status`` setting — a list of
    ``ClassSection.CLASS_STATUS`` codes (the stored values are codes such as
    ``'A'``, not labels such as ``'Active'``). An empty or absent selection
    means every status qualifies, so no filter is applied.

    Shared by the "Previous Year" column and the copy-last-year's-sections
    prefill so the two can never disagree about which classes count.
    """
    return {'status__in': list(statuses)} if statuses else {}


def build_prev_year_lookup(previous_academic_year_id, statuses=None):
    """Return ``{f'{course_id}_{highschool_id}': [{term_name, count}, …]}``
    of previous-year section counts.

    Feeds the "Previous Year" column in both the HS admin and the CE portal,
    which is why it lives here rather than in either view.

    *statuses* is the tenant's ``prev_year_class_status`` setting — a list of
    ``ClassSection.CLASS_STATUS`` codes (the stored values are codes such as
    ``'A'``, not labels such as ``'Active'``). When it is empty or absent,
    classes of every status are counted.
    """
    from django.db.models import Count
    from cis.models.section import ClassSection

    lookup = {}
    if not previous_academic_year_id:
        return lookup

    filters = {'term__academic_year__id': previous_academic_year_id}
    filters.update(prev_year_status_filter(statuses))

    rows = (
        ClassSection.objects.filter(**filters)
        .values('course_id', 'highschool_id', 'term__id', 'term__label')
        .annotate(count=Count('id'))
    )
    for row in rows:
        key = f"{row['course_id']}_{row['highschool_id']}"
        lookup.setdefault(key, []).append({
            'term_name': row['term__label'],
            'count': row['count'],
        })
    return lookup


def build_initial_from_prev_year(teacher_course):
    """Build formset initial data from previous year ClassSections using term mapping.

    Collapses to one row per previous-year term. Maps terms using the
    ``term_mapping`` stored in settings. Unmapped terms get a blank term value.
    """
    import json
    from cis.models.section import ClassSection

    fs_config = get_fs_config()
    previous_academic_year_id = fs_config.get('previous_academic_year')
    if not previous_academic_year_id:
        return []

    try:
        term_mapping = json.loads(fs_config.get('term_mapping', '{}'))
    except (json.JSONDecodeError, TypeError):
        term_mapping = {}

    if not term_mapping:
        return []

    highschool = teacher_course.teacher_highschool.highschool
    teacher = teacher_course.teacher_highschool.teacher
    course = teacher_course.course

    prev_sections = ClassSection.objects.filter(
        term__academic_year__id=previous_academic_year_id,
        highschool=highschool,
        teacher=teacher,
        course=course,
        **prev_year_status_filter(fs_config.get('prev_year_class_status')),
    ).select_related('term').order_by('term__code')

    seen_terms = set()
    initial_data = []
    for section in prev_sections:
        prev_term_id = str(section.term_id)
        if prev_term_id in seen_terms:
            continue
        seen_terms.add(prev_term_id)

        mapped_term_id = term_mapping.get(prev_term_id, '')
        initial_data.append({
            'term': mapped_term_id or '',
            'highschool_course_name': section.highschool_course_name or '',
        })

    return initial_data


def get_user_context(request):
    """
    Get the user's role context for future sections operations.

    Returns a dict with:
    - highschools: QuerySet of accessible highschools
    - teacher: Teacher instance (if instructor) or None
    - is_admin: True if user is a highschool admin

    Args:
        request: HTTP request with authenticated user

    Returns:
        dict with user context information
    """
    if user_has_highschool_admin_role(request.user):
        hs_admin = HSAdministrator.objects.get(user=request.user)
        return {
            'highschools': hs_admin.get_highschools(),
            'teacher': None,
            'is_admin': True
        }
    elif user_has_instructor_role(request.user):
        teacher = Teacher.objects.get(user=request.user)
        teacher_hs = teacher.get_highschools(teacher)
        return {
            'highschools': HighSchool.objects.filter(
                id__in=teacher_hs.values_list('highschool__id')
            ),
            'teacher': teacher,
            'is_admin': False
        }
    else:
        raise PermissionDenied("User is not an instructor or highschool administrator")


def validate_certificate_access(request, teacher_course):
    """
    Verify user can access this TeacherCourseCertificate.

    For HS Admins: Certificate must be for a highschool they manage
    For Instructors: Certificate must belong to them

    Args:
        request: HTTP request with authenticated user
        teacher_course: TeacherCourseCertificate instance

    Raises:
        PermissionDenied: If user cannot access the certificate
    """
    context = get_user_context(request)

    if context['is_admin']:
        if teacher_course.teacher_highschool.highschool not in context['highschools']:
            raise PermissionDenied("No access to this highschool")
    else:
        if teacher_course.teacher_highschool.teacher != context['teacher']:
            raise PermissionDenied("You do not have permission to access this course")


def get_or_create_future_projection(highschool_id, user):
    """
    Get or create a FutureProjection for a highschool and academic year.

    Args:
        highschool_id: UUID of the highschool
        user: The user creating the projection

    Returns:
        FutureProjection instance
    """
    fs_config = get_fs_config()
    academic_year_id = fs_config.get('academic_year')

    projection = FutureProjection.objects.filter(
        highschool__id=highschool_id,
        academic_year__id=academic_year_id
    ).first()

    if not projection:
        projection = FutureProjection.objects.create(
            highschool=HighSchool.objects.get(pk=highschool_id),
            academic_year=AcademicYear.objects.get(pk=academic_year_id),
            created_by=user,
            meta={
                'confirmed_administrators': 'No',
                'confirmed_class_sections': 'No',
                'history': []
            }
        )

    return projection


class ExistingAccountNotApplicantError(Exception):
    """Raised by ``get_or_create_applicant`` when *email* already belongs to
    an existing account that holds a role other than ``applicant``.

    Reusing such an account would attach an applicant record to someone's
    existing, possibly privileged, login and email them a verification link
    into the applicant flow — so no account is touched and no mail of any
    kind is sent when this is raised.
    """

    def __init__(self, email):
        self.email = email
        super().__init__(
            f'{email} already belongs to an existing account that is not '
            'an applicant.')


def get_or_create_applicant(email, full_name):
    """Return ``(TeacherApplicant, created)`` for *email*.

    Reuses an existing user and applicant rather than creating a second
    account for the same address. The applicant is left unverified: the
    caller sends the verification email so the recipient proves they control
    the address before they can set a password.

    Raises:
        ExistingAccountNotApplicantError: if an existing account matches
            *email* and holds any role other than ``applicant`` (e.g.
            instructor, student, ce). A user with no roles at all is fine
            to reuse.
    """
    import importlib.util
    from cis.models.customuser import CustomUser

    if importlib.util.find_spec('instructor_app.instructor_app'):
        from instructor_app.instructor_app.models.teacher_applicant_model \
            import TeacherApplicant
    else:
        from instructor_app.models.teacher_applicant_model import (
            TeacherApplicant)

    first_name, _, last_name = (full_name or '').strip().partition(' ')

    user = CustomUser.objects.filter(email__iexact=email).first()
    if user is None:
        user = CustomUser.objects.create(
            username=email, email=email,
            first_name=first_name, last_name=last_name)
    else:
        roles = user.get_roles()
        if any(role != 'applicant' for role in roles):
            raise ExistingAccountNotApplicantError(email)

    applicant = TeacherApplicant.objects.filter(user=user).first()
    if applicant is not None:
        return applicant, False

    return TeacherApplicant.objects.create(user=user), True


def add_history_entry(obj, user, action):
    """
    Add a history entry to an object's meta field.

    Args:
        obj: Object with a meta JSONField (FutureCourse or FutureProjection)
        user: User performing the action
        action: Description of the action
    """
    if not obj.meta:
        obj.meta = {'history': []}

    if 'history' not in obj.meta:
        obj.meta['history'] = []

    obj.meta['history'].append({
        'user': str(user),
        'action': action,
        'on': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


def get_user_highschools(request):
    """
    Get the highschools accessible to the user.

    Args:
        request: HTTP request with authenticated user

    Returns:
        QuerySet of HighSchool instances
    """
    context = get_user_context(request)
    return context['highschools']


def get_course_certificates_for_user(request):
    """Return the certs the user should see for the current cycle.

    Universe is anchored on lookback Sections (see get_lookback_universe),
    not just cert status. Course status is still applied as a final filter
    so a cert tied to an Inactive Course is excluded.
    """
    fs_config = get_fs_config()
    context = get_user_context(request)

    universe = get_lookback_universe()  # cross-school
    course_status = fs_config.get('course_status') or []
    if course_status:
        universe = universe.filter(course__status__in=course_status)

    if context['is_admin']:
        return universe.filter(
            teacher_highschool__highschool__in=context['highschools'],
        )
    else:
        return universe.filter(
            teacher_highschool__teacher=context['teacher'],
        )


def get_lookback_universe(highschool=None):
    """
    Return TeacherCourseCertificate queryset of teachers expected to respond
    to the current cycle. Anchored on ClassSections in `lookback_terms` with
    status='A' (Active). When `allow_new_teacher_create='1'` is set, Applicant
    certs are unioned in even if the teacher has no Section history.

    Args:
        highschool: Optional HighSchool instance to scope the query.
                    None returns the universe across all schools.

    Returns:
        QuerySet of TeacherCourseCertificate.
    """
    from cis.models.section import ClassSection

    fs_config = get_fs_config()
    lookback_term_ids = fs_config.get('lookback_terms') or []
    if not lookback_term_ids:
        return TeacherCourseCertificate.objects.none()

    cert_status_filter = fs_config.get('teacher_course_status') or []

    # (teacher_id, course_id) pairs that actually taught in lookback_terms.
    taught = ClassSection.objects.filter(
        term__id__in=lookback_term_ids,
        status='A',
    )
    if highschool is not None:
        taught = taught.filter(highschool=highschool)
    taught_pairs = taught.values_list('teacher_id', 'course_id').distinct()

    if not taught_pairs:
        behaviour_qs = TeacherCourseCertificate.objects.none()
    else:
        # Build a Q-disjunction so we match each pair exactly. For tenants with
        # large lookback sets this could be optimized; keep simple for now.
        from django.db.models import Q
        q = Q()
        for teacher_id, course_id in taught_pairs:
            q |= Q(
                teacher_highschool__teacher_id=teacher_id,
                course_id=course_id,
            )
        behaviour_qs = TeacherCourseCertificate.objects.filter(q)
        if cert_status_filter:
            behaviour_qs = behaviour_qs.filter(status__in=cert_status_filter)
        if highschool is not None:
            behaviour_qs = behaviour_qs.filter(
                teacher_highschool__highschool=highschool)

    # Applicant carve-out
    if fs_config.get('allow_new_teacher_create') == '1':
        applicant_qs = TeacherCourseCertificate.objects.filter(
            status='Applicant',
        )
        if highschool is not None:
            applicant_qs = applicant_qs.filter(
                teacher_highschool__highschool=highschool)
        return (behaviour_qs | applicant_qs).distinct()

    return behaviour_qs.distinct()


def build_section_info_from_formset(request, teaching_formset, future_course):
    """
    Convert a validated teaching formset into the section_info payload
    persisted on FutureCourse.section_info['sections'].

    Per section it:
      - Skips empty rows (no `term`).
      - Uploads any `form-<i>-syllabus` file to PrivateMediaStorage and stores
        the resulting URL in cleaned_data['file'].
      - Drops the raw UploadedFile (`syllabus` key) since UploadedFile is not
        JSON-serializable; cleaned_data['file'] holds the saved URL instead.
      - Uploads any `form-<i>-<name>` file for each schema file field and
        stores the resulting URL under that field's own key. When nothing
        new is posted, the value already on the field (hidden file field
        case) or its `<name>_existing` companion (visible file field case)
        is carried forward only when it matches a URL already stored under
        that key somewhere on the record; otherwise the field is stored as
        `''`.

    Args:
        request: Current HttpRequest (used for request.FILES).
        teaching_formset: A bound, validated TeachingFormSet.
        future_course: FutureCourse (used in the storage path).

    Returns:
        list[dict]: cleaned_data dicts ready to assign to
        FutureCourse.section_info['sections'].
    """
    from cis.backends.storage_backend import PrivateMediaStorage
    from django.utils.text import get_valid_filename

    existing_sections = (future_course.section_info or {}).get(
        'sections', []) or []
    known_urls = {
        name: {
            section.get(name)
            for section in existing_sections
            if section.get(name)
        }
        for name in TeachingSectionFieldSchema.get_file_field_names()
    }

    sections = []
    for index, teaching_form in enumerate(teaching_formset):
        cleaned = teaching_form.cleaned_data
        if not cleaned or not cleaned.get('term'):
            continue

        uploaded = request.FILES.get(f'form-{index}-syllabus')
        if uploaded:
            storage = PrivateMediaStorage()
            safe_name = get_valid_filename(uploaded.name)
            stored_path = storage.save(
                f'future_section/{future_course.id}/{safe_name}',
                uploaded,
            )
            cleaned['file'] = storage.url(stored_path)

        cleaned.pop('syllabus', None)

        # Schema-driven file fields store their URL under their own key.
        for file_name in TeachingSectionFieldSchema.get_file_field_names():
            uploaded = request.FILES.get(f'form-{index}-{file_name}')
            if uploaded:
                storage = PrivateMediaStorage()
                safe_name = get_valid_filename(uploaded.name)
                stored_path = storage.save(
                    f'future_section/{future_course.id}/{safe_name}',
                    uploaded,
                )
                cleaned[file_name] = storage.url(stored_path)
            else:
                # No new upload this request. The posted value — whether it
                # arrives as cleaned[file_name] (hidden file field) or as the
                # `_existing` companion (visible file field) — is
                # client-supplied and untrusted. Only accept it when it
                # matches a URL already stored under this key on the record
                # (any section, since rows can be added/removed/reordered);
                # otherwise store ''.
                candidate = (cleaned.get(file_name)
                             or cleaned.get(f'{file_name}_existing', ''))
                cleaned[file_name] = (
                    candidate
                    if candidate in known_urls.get(file_name, set())
                    else '')
            cleaned.pop(f'{file_name}_existing', None)

        sections.append(cleaned)
    return sections
