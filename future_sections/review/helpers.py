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

from ..models import FutureCourse, SectionRequestReview
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
    """Requests the user holds a review slot on, in any round.

    Membership of the snapshot — not the live CourseAdministrator rows —
    is the gate, so deactivating a reviewer mid-round does not strand the
    request and adding one does not pull them into a running round.
    """
    if not user.is_authenticated:
        return FutureCourse.objects.none()
    return FutureCourse.objects.filter(
        reviews__reviewer=user,
    ).distinct().select_related(
        'teacher_course__course',
        'teacher_course__teacher_highschool__highschool',
        'teacher_course__teacher_highschool__teacher__user',
        'academic_year',
        'submitted_by',
    )


def pending_for(user):
    """Requests awaiting this user's decision in the live round."""
    from django.db.models import F
    return visible_future_courses_for(user).filter(
        status='pending_review',
        reviews__reviewer=user,
        reviews__round=F('review_round'),
        reviews__decision='',
    )


def reviewed_for(user):
    """Requests this user has already decided on, any round or status."""
    from django.db.models import Exists, OuterRef

    decided = SectionRequestReview.objects.filter(
        future_course=OuterRef('pk'), reviewer=user,
    ).exclude(decision='')
    return visible_future_courses_for(user).filter(Exists(decided))


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


class NoReviewersError(Exception):
    """No qualifying reviewer exists, so the round could never complete."""


class NotAReviewerError(Exception):
    """The user has no slot in the request's live review round."""


def qualifying_reviewers(future_course):
    """(user, role) pairs eligible to review *future_course* right now."""
    roles = get_reviewer_roles()
    admins = CourseAdministrator.objects.filter(
        course=future_course.teacher_course.course,
        role__in=roles, status='Active',
    ).select_related('user')
    seen, pairs = set(), []
    for admin in admins:
        if admin.user_id in seen:
            continue
        seen.add(admin.user_id)
        pairs.append((admin.user, admin.role))
    return pairs


def open_review_round(future_course):
    """Snapshot the reviewers, lock the request, return the new round."""
    pairs = qualifying_reviewers(future_course)
    if not pairs:
        raise NoReviewersError(
            'No qualifying reviewer for this course.')

    round_number = (future_course.review_round or 0) + 1
    with transaction.atomic():
        SectionRequestReview.objects.bulk_create([
            SectionRequestReview(
                future_course=future_course, reviewer=user,
                round=round_number, role=role,
            )
            for user, role in pairs
        ])
        future_course.review_round = round_number
        future_course.status = 'pending_review'
        future_course.save(update_fields=['review_round', 'status'])
    return round_number


def record_decision(future_course, reviewer, *, decision, comment='',
                    mentor=None):
    """Fill in *reviewer*'s slot, advancing the request when it is the last."""
    try:
        row = SectionRequestReview.objects.get(
            future_course=future_course, reviewer=reviewer,
            round=future_course.review_round,
        )
    except SectionRequestReview.DoesNotExist:
        raise NotAReviewerError(
            'You are not a reviewer on this round.')

    row.decision = decision
    row.comment = comment or ''
    row.mentor = mentor
    row.decided_on = timezone.now()
    row.save(update_fields=['decision', 'comment', 'mentor', 'decided_on'])

    if round_is_complete(future_course):
        future_course.status = 'reviewed'
        future_course.save(update_fields=['status'])
    return row


def round_is_complete(future_course):
    """True when every slot in the live round has a decision."""
    return not future_course.reviews.filter(
        round=future_course.review_round, decision='',
    ).exists()


def reset_review(future_course):
    """Return the request to `submitted` and unlock it.

    Rows from the finished round keep their round number and are left
    untouched — they are the history. The next `open_review_round` opens
    round N+1.
    """
    future_course.status = 'submitted'
    future_course.save(update_fields=['status'])


def is_locked(future_course):
    """True when the school may no longer edit this request."""
    return future_course.status in FutureCourse.LOCKED_STATUSES
