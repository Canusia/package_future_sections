"""Section-request review views. Portal-agnostic; mounted twice."""
import json
import logging

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404
from django.shortcuts import render, redirect
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.clickjacking import xframe_options_exempt

from cis.models.course import CourseAdministrator
from cis.models.term import AcademicYear
from cis.menu import draw_menu, FACULTY_MENU, cis_menu

from ..models import SectionRequestReview
from ..settings.future_sections import future_sections as fs_settings
from ..schemas import TeachingSectionFieldSchema

from .forms import SectionRequestReviewForm
from .helpers import (
    visible_future_courses_for,
    create_or_attach_mentor,
    record_decision,
    NotAReviewerError,
    review_required,
    mentor_assignment_enabled,
    get_mentor_role,
)

logger = logging.getLogger(__name__)


# Per-portal configuration. Each shim picks one of these.
_PORTAL_CONFIG = {
    'faculty': {
        'menu_def': FACULTY_MENU,
        'menu_key': 'section_requests',
        'menu_submenu': '',
        'menu_portal': 'faculty',
        'back_url': 'faculty:dashboard',
        'api_url': '/faculty/future_sections/section_request_api/section_request/',
        'detail_url_name': 'future_sections_faculty:section_request_detail',
    },
    'ce': {
        'menu_def': cis_menu,
        'menu_key': 'classes',
        'menu_submenu': 'future_sections',
        'menu_portal': 'ce',
        'back_url': 'cis:dashboard',
        'api_url': '/ce/future_sections/section_request_api/section_request/',
        'detail_url_name': 'future_sections_ce:section_request_detail',
    },
}


def _get_visible_or_404(request, future_course_id):
    qs = visible_future_courses_for(request.user)
    fc = qs.filter(id=future_course_id).first()
    if not fc:
        raise Http404('Section request not visible')
    return fc


def _initial_from_row(row, course=None, mentor_role='Faculty'):
    if not row or not row.decision:
        return {}
    initial = {
        'decision': row.decision,
        'comment': row.comment,
    }
    if course is not None and row.mentor_id:
        ca = CourseAdministrator.objects.filter(
            course=course, user_id=row.mentor_id,
            role=mentor_role, status='Active',
        ).first()
        if ca:
            initial['existing_mentor'] = ca.id
    return initial


def _section_value(sec, name):
    if name == 'term':
        return sec.get('term_name') or sec.get('term') or ''
    return sec.get(name, '')


def _teaching_form_config():
    try:
        raw = fs_settings.from_db().get('teaching_form_config')
    except Exception:
        logger.warning('Failed to read teaching_form_config', exc_info=True)
        return {}
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) or {}
    except (TypeError, ValueError):
        return {}


def _default_field_label(name):
    meta = TeachingSectionFieldSchema.get_field_meta(name) or {}
    return meta.get('default_label') or name.replace('_', ' ').title()


def _section_field_specs(cfg):
    cfg = cfg or {}
    visible_names = cfg.get('fields') or []
    labels = cfg.get('labels') or {}
    weights = cfg.get('weights') or {}
    if not isinstance(visible_names, list):
        visible_names = []
    if 'term' not in visible_names:
        visible_names = ['term'] + list(visible_names)
    decorated = []
    for name in visible_names:
        weight = 0
        if isinstance(weights, dict):
            try:
                weight = int(weights.get(name) or 0)
            except (TypeError, ValueError):
                weight = 0
        if name == 'term':
            weight = -1
        label = (labels.get(name) if isinstance(labels, dict) else None) \
            or _default_field_label(name)
        decorated.append((weight, name, label))
    decorated.sort(key=lambda t: t[0])
    return [(name, label) for _w, name, label in decorated]


def _check_review_enabled():
    if not review_required():
        raise Http404('Review is disabled.')


@login_required
def section_request_list(request, *, portal):
    _check_review_enabled()
    cfg = _PORTAL_CONFIG[portal]
    academic_years = AcademicYear.objects.all().order_by('-name')
    selected_ay_id = request.GET.get('academic_year')
    if not selected_ay_id and academic_years:
        selected_ay_id = str(academic_years[0].id)

    menu = draw_menu(cfg['menu_def'], cfg['menu_key'], cfg['menu_submenu'], cfg['menu_portal'])

    return render(
        request,
        'future_sections/review/list.html',
        {
            'page_title': 'Section Requests',
            'menu': menu,
            'academic_years': academic_years,
            'selected_ay_id': selected_ay_id,
            'api_url': cfg['api_url'],
            'back_url': cfg['back_url'],
        },
    )


@xframe_options_exempt
@login_required
def section_request_detail(request, future_course_id, *, portal):
    _check_review_enabled()
    cfg = _PORTAL_CONFIG[portal]
    fc = _get_visible_or_404(request, future_course_id)
    course = fc.teacher_course.course
    mentor_role = get_mentor_role()
    require_mentor = mentor_assignment_enabled()

    if request.method == 'POST':
        form = SectionRequestReviewForm(
            request.POST, course=course,
            mentor_role=mentor_role, require_mentor=require_mentor,
        )
        if form.is_valid():
            decision = form.cleaned_data['decision']
            comment = form.cleaned_data['comment']
            mentor_user = None
            if decision == 'approved' and require_mentor:
                if form.has_existing_options:
                    mentor_user = form.cleaned_data['existing_mentor'].user
                else:
                    mentor_user = create_or_attach_mentor(
                        course,
                        name=form.cleaned_data['new_mentor_name'],
                        email=form.cleaned_data['new_mentor_email'],
                        role=mentor_role,
                    )
            try:
                record_decision(
                    fc, request.user,
                    decision=decision, comment=comment,
                    mentor=mentor_user,
                )
            except NotAReviewerError:
                raise Http404('Not a reviewer on this round')
            messages.success(request, 'Review submitted.')
            return redirect(cfg['detail_url_name'], future_course_id=fc.id)
    live_rows = fc.reviews.filter(round=fc.review_round).select_related('reviewer')
    my_row = live_rows.filter(reviewer=request.user).first()

    if request.method != 'POST':
        form = SectionRequestReviewForm(
            initial=_initial_from_row(my_row, course=course, mentor_role=mentor_role),
            course=course, mentor_role=mentor_role, require_mentor=require_mentor,
        )

    other_decisions = [
        {'reviewer_name': f'{r.reviewer.first_name} {r.reviewer.last_name}'.strip()
                          or r.reviewer.username,
         'decision': dict(SectionRequestReview.DECISION_CHOICES).get(
             r.decision, ''),
         'comment': r.comment,
         'decided_on': r.decided_on}
        for r in live_rows.exclude(reviewer=request.user) if r.decision
    ]
    teaching_form_config = _teaching_form_config()
    field_specs = _section_field_specs(teaching_form_config)
    show_syllabus = bool(teaching_form_config.get('show_syllabus'))

    sections = (fc.section_info or {}).get('sections') or []
    rendered_sections = []
    for sec in sections:
        row = [(label, _section_value(sec, name)) for name, label in field_specs]
        if show_syllabus and sec.get('file'):
            row.append(('Syllabus', mark_safe(
                f'<a href="{escape(sec["file"])}" target="_blank">Download</a>'
            )))
        rendered_sections.append(row)

    menu = draw_menu(cfg['menu_def'], cfg['menu_key'], cfg['menu_submenu'], cfg['menu_portal'])

    return render(
        request,
        'future_sections/review/detail.html',
        {
            'page_title': 'Review Section Request',
            'menu': menu,
            'fc': fc,
            'course': course,
            'highschool': fc.teacher_course.teacher_highschool.highschool,
            'instructor': fc.teacher_course.teacher_highschool.teacher.user,
            'my_row': my_row,
            'other_decisions': other_decisions,
            'rendered_sections': rendered_sections,
            'form': form,
            'has_existing_mentor_options': form.has_existing_options,
            'assign_mentor': require_mentor,
        },
    )
