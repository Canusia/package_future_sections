"""
Section-request review helpers.

NOTE: The `section_info['faculty_review']` JSON key is named for historical
reasons (the review flow originally lived in the `faculty` app). It now
represents review by any qualifying CourseAdministrator role configured
in the `cis_future_sections` setting.
"""
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.utils import timezone

from cis.models.course import CourseAdministrator

from ..models import FutureCourse
from ..settings.future_sections import future_sections as fs_settings


DEFAULT_REVIEWER_ROLES = ['Faculty', 'Dept. Chair', 'Dean']
DEFAULT_MENTOR_ROLE = 'Faculty'


def _settings():
    try:
        return fs_settings.from_db() or {}
    except Exception:
        return {}


def get_reviewer_roles():
    """Return list of CourseAdministrator role values allowed to review."""
    cfg = _settings()
    roles = cfg.get('reviewer_roles') or DEFAULT_REVIEWER_ROLES
    # Stored as either a list or a CheckboxSelectMultiple's value list.
    return list(roles) if isinstance(roles, (list, tuple)) else DEFAULT_REVIEWER_ROLES


def get_mentor_role():
    """Return the CourseAdministrator role to assign to mentors."""
    cfg = _settings()
    return cfg.get('mentor_default_role') or DEFAULT_MENTOR_ROLE


def review_required():
    """True when the settings say proposals must be reviewed."""
    return _settings().get('require_review') == 'Yes' \
        or _settings().get('require_review') == '1'


def mentor_assignment_enabled():
    """True when an approval should collect a mentor."""
    return _settings().get('assign_mentor') == 'Yes' \
        or _settings().get('assign_mentor') == '1'


def visible_future_courses_for(user):
    """FutureCourse rows the user is allowed to see and review."""
    if not user.is_authenticated:
        return FutureCourse.objects.none()
    roles = get_reviewer_roles()
    course_ids = CourseAdministrator.objects.filter(
        user=user, role__in=roles, status='Active',
    ).values_list('course_id', flat=True)
    return FutureCourse.objects.filter(
        teacher_course__course_id__in=course_ids,
    ).select_related(
        'teacher_course__course',
        'teacher_course__teacher_highschool__highschool',
        'teacher_course__teacher_highschool__teacher__user',
        'academic_year',
        'submitted_by',
    )


def get_faculty_review(future_course):
    """Return the faculty_review dict, or None if no review yet."""
    info = future_course.section_info or {}
    return info.get('faculty_review')


def is_pending(future_course):
    review = get_faculty_review(future_course)
    return not review or not review.get('decision')


def save_faculty_review(future_course, *, decision, comment, mentor, reviewer):
    """Update section_info.faculty_review with the new decision."""
    info = dict(future_course.section_info or {})
    prior = info.get('faculty_review') or {}
    history = list(prior.get('history') or [])
    if prior.get('decision'):
        history.append({
            'decision': prior.get('decision'),
            'comment': prior.get('comment', ''),
            'mentor': prior.get('mentor'),
            'reviewer_id': prior.get('reviewer_id'),
            'reviewer_name': prior.get('reviewer_name'),
            'reviewed_on': prior.get('reviewed_on'),
        })
    info['faculty_review'] = {
        'decision': decision,
        'comment': comment or '',
        'mentor': mentor,
        'reviewer_id': str(reviewer.id),
        'reviewer_name': f'{reviewer.first_name} {reviewer.last_name}'.strip() or reviewer.username,
        'reviewed_on': timezone.now().isoformat(),
        'history': history,
    }
    future_course.section_info = info
    future_course.save(update_fields=['section_info'])


def create_or_attach_mentor(course, *, name, email, role=None):
    """
    Create-or-attach a mentor on `course`. User is always faculty-group +
    FacultyCoordinator; the CourseAdministrator row uses `role` (defaults
    to the configured mentor_default_role).

    Returns the CustomUser.
    """
    from cis.models.customuser import CustomUser
    from cis.models.faculty import FacultyCoordinator

    role = role or get_mentor_role()
    parts = (name or '').strip().split(None, 1)
    first_name = parts[0] if parts else ''
    last_name = parts[1] if len(parts) > 1 else ''

    with transaction.atomic():
        user, created = _get_or_create_mentor_user(
            CustomUser, email=email,
            first_name=first_name, last_name=last_name,
        )
        faculty_group, _ = Group.objects.get_or_create(name='faculty')
        user.groups.add(faculty_group)
        FacultyCoordinator.objects.get_or_create(
            user=user, defaults={'status': 'Active'})

        admin = CourseAdministrator.get_or_add(course=course, user=user, role=role)
        if admin.status != 'Active':
            admin.status = 'Active'
            admin.save(update_fields=['status'])

    if created:
        try:
            user.send_password_reset_email()
        except Exception:
            pass
    return user


def _get_or_create_mentor_user(CustomUser, *, email, first_name, last_name):
    user = (
        CustomUser.objects.filter(email__iexact=email).first()
        or CustomUser.objects.filter(username__iexact=email).first()
    )
    if user:
        return user, False
    try:
        user = CustomUser.objects.create(
            username=email, email=email,
            first_name=first_name, last_name=last_name,
        )
    except IntegrityError:
        user = (
            CustomUser.objects.filter(email__iexact=email).first()
            or CustomUser.objects.filter(username__iexact=email).first()
        )
        if not user:
            raise
        return user, False
    user.set_unusable_password()
    user.save(update_fields=['password'])
    return user, True
