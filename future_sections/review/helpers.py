"""
Section-request review helpers.

NOTE: The `section_info['faculty_review']` JSON key is named for historical
reasons (the review flow originally lived in the `faculty` app). It now
represents review by any qualifying CourseAdministrator role configured
in the `cis_future_sections` setting.
"""
import json
import logging

from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.utils import timezone

from cis.models.course import CourseAdministrator

from ..models import FutureCourse, SectionRequestReview
from ..settings.future_sections import future_sections as fs_settings


logger = logging.getLogger(__name__)

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


def get_reviewer_weights():
    """Return `{role: weight}` for every configured reviewer role.

    Lower weight is asked first; roles sharing a weight form one stage. A
    role the config omits weighs 0, and an absent or unparsable config
    weighs every role 0 — one stage, i.e. exactly the parallel behaviour
    this replaced.
    """
    cfg = _settings()
    raw = cfg.get('reviewer_role_config') or ''
    parsed = {}
    if isinstance(raw, dict):
        parsed = raw
    elif raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                parsed = loaded
        except (ValueError, TypeError):
            parsed = {}

    weights = {}
    for role in get_reviewer_roles():
        value = parsed.get(role, 0)
        weights[role] = value if isinstance(value, int) and not isinstance(
            value, bool) else 0
    return weights


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
    """Requests awaiting this user's decision **in the current stage**.

    A later-stage reviewer still sees the request (see
    `visible_future_courses_for`) but it is not in their queue until their
    stage opens — otherwise "only the first reviewer is asked" would be
    contradicted by the queue itself. A paused request is in nobody's
    queue: staff drive it by hand.

    The stage test is deliberately a single correlated `Exists` over *this
    user's own* undecided row, with a nested `Exists` asking whether any
    earlier-weight row on the **same** request and round is still
    undecided. Expressing it as chained `.filter()` calls across the
    multi-valued `reviews` relation would instead produce independent
    joins, and could match a request whose *minimum* undecided weight
    belongs to somebody else's row — leaking a later stage's request into
    this user's queue.
    """
    from django.db.models import Exists, OuterRef

    earlier_undecided = SectionRequestReview.objects.filter(
        future_course=OuterRef('future_course'),
        round=OuterRef('round'),
        weight__lt=OuterRef('weight'),
        decision='',
    )
    my_current_stage_row = SectionRequestReview.objects.filter(
        future_course=OuterRef('pk'),
        round=OuterRef('review_round'),
        reviewer=user,
        decision='',
    ).exclude(Exists(earlier_undecided))

    return visible_future_courses_for(user).filter(
        status='pending_review',
        review_paused_on__isnull=True,
    ).filter(Exists(my_current_stage_row)).distinct()


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
    """(user, role, weight) triples eligible to review *future_course* now.

    One entry per user: someone holding several qualifying roles is asked
    once, under their **lowest-weight** role, so a Dean-and-Faculty is
    asked at the earlier stage rather than twice. Sorted by weight, so the
    snapshot reads in stage order.
    """
    weights = get_reviewer_weights()
    admins = CourseAdministrator.objects.filter(
        course=future_course.teacher_course.course,
        role__in=list(weights.keys()), status='Active',
    ).select_related('user')

    best = {}
    for admin in admins:
        weight = weights.get(admin.role, 0)
        current = best.get(admin.user_id)
        if current is None or weight < current[2]:
            best[admin.user_id] = (admin.user, admin.role, weight)
    return sorted(best.values(), key=lambda triple: triple[2])


def open_review_round(future_course):
    """Snapshot the reviewers, lock the request, notify the first stage."""
    triples = qualifying_reviewers(future_course)
    if not triples:
        raise NoReviewersError(
            'No qualifying reviewer for this course.')

    round_number = (future_course.review_round or 0) + 1
    with transaction.atomic():
        SectionRequestReview.objects.bulk_create([
            SectionRequestReview(
                future_course=future_course, reviewer=user,
                round=round_number, role=role, weight=weight,
            )
            for user, role, weight in triples
        ])
        future_course.review_round = round_number
        future_course.status = 'pending_review'
        future_course.review_paused_on = None
        future_course.save(update_fields=[
            'review_round', 'status', 'review_paused_on'])

    _notify_current_stage(future_course)
    return round_number


def current_stage(future_course):
    """Lowest weight still awaiting a decision in the live round.

    None when nothing is outstanding — the round is finished, or no round
    has been opened.
    """
    return future_course.reviews.filter(
        round=future_course.review_round, decision='',
    ).order_by('weight').values_list('weight', flat=True).first()


def stage_rows(future_course, stage=None):
    """Live-round rows at *stage* (default: the current stage)."""
    if stage is None:
        stage = current_stage(future_course)
    if stage is None:
        return SectionRequestReview.objects.none()
    return future_course.reviews.filter(
        round=future_course.review_round, weight=stage,
    ).select_related('reviewer')


def _notify_current_stage(future_course):
    """Email the current stage's undecided reviewers that it is their turn.

    Silent when the request is paused or nothing is outstanding. Mail
    failures must not roll back a recorded decision, so this never raises.
    """
    from ..models import FutureCourse as _FutureCourse

    if future_course.is_review_paused:
        return
    stage = current_stage(future_course)
    if stage is None:
        return
    try:
        _FutureCourse.notify_review_stage(future_course, stage)
    except Exception:  # pragma: no cover - notification is best effort
        logger.exception('Failed to notify review stage')


def record_decision(future_course, reviewer, *, decision, comment='',
                    mentor=None):
    """Fill in *reviewer*'s slot, advancing the request when it is the last."""
    if future_course.status != 'pending_review':
        raise NotAReviewerError(
            'This request is not open for review.')

    try:
        row = SectionRequestReview.objects.get(
            future_course=future_course, reviewer=reviewer,
            round=future_course.review_round,
        )
    except SectionRequestReview.DoesNotExist:
        raise NotAReviewerError(
            'You are not a reviewer on this round.')

    # Only the current stage may decide. `visible_future_courses_for` (and
    # so the detail view) spans every round and stage, so without this a
    # later-stage reviewer could post before their turn: that would re-fire
    # the current stage's notification and let them pause a stage that is
    # not theirs.
    if row.weight != current_stage(future_course):
        raise NotAReviewerError(
            'This request is not at your review stage.')

    row.decision = decision
    row.comment = comment or ''
    row.mentor = mentor
    row.decided_on = timezone.now()
    row.save(update_fields=['decision', 'comment', 'mentor', 'decided_on'])

    if decision == 'not_approved':
        # Pause rather than advance: no further reviewer is notified until
        # staff act. The rest of the stage keeps its undecided rows — they
        # are simply no longer chased.
        future_course.review_paused_on = timezone.now()
        future_course.save(update_fields=['review_paused_on'])
        _escalate_denial(row)
        return row

    if _stage_is_complete(future_course, row.weight):
        advance_or_finish(future_course)
    return row


def _stage_is_complete(future_course, stage):
    """True when every row at *stage* in the live round has decided."""
    return not future_course.reviews.filter(
        round=future_course.review_round, weight=stage, decision='',
    ).exists()


def _escalate_denial(row):
    """Tell staff a reviewer did not approve. Never raises."""
    from ..models import FutureCourse as _FutureCourse

    try:
        _FutureCourse.notify_review_escalation(row)
    except Exception:  # pragma: no cover - notification is best effort
        logger.exception('Failed to send review escalation')


def advance_or_finish(future_course):
    """Open the next stage, or mark the request reviewed when none is left.

    Returns the new stage's weight, or None when the request was finished.

    A paused request never advances or completes: the single choke point
    for every status transition is here, so the pause check lives here too
    rather than being repeated at each caller. Without it a stage peer's
    approval after somebody's denial would complete the round with the
    pause still set -- deny-then-approve finishing what approve-then-deny
    pauses. `resume_review` clears the pause *before* calling this, so the
    staff resume path is unaffected.

    The guard reads `future_course.review_paused_on` fresh from the
    database first: two same-stage reviewers posting in the same window
    can otherwise see a stale in-memory `future_course` that predates a
    concurrent denial's commit, letting the guard see False and complete
    the round with the pause still set underneath it. `resume_review`
    saves its own clear before calling here, so this refresh only ever
    picks up that same cleared value, not a stale pause.
    """
    future_course.refresh_from_db(fields=['review_paused_on'])
    if future_course.is_review_paused:
        return None
    stage = current_stage(future_course)
    if stage is None:
        future_course.status = 'reviewed'
        future_course.save(update_fields=['status'])
        return None
    _notify_current_stage(future_course)
    return stage


def resume_review(future_course):
    """Staff gesture after a denial: clear the pause and carry on.

    The denial stays on the record as history. Returns the weight of the
    stage that was re-notified -- the *current* stage, which is still the
    denier's own when a stage peer has yet to decide, and the following one
    once the stage is complete -- or None when nothing was outstanding (the
    request is marked reviewed instead).
    """
    future_course.review_paused_on = None
    future_course.save(update_fields=['review_paused_on'])
    return advance_or_finish(future_course)


def round_is_complete(future_course):
    """True when every slot in the live round has a decision.

    Caveat: this no longer implies the request is `reviewed`. A round whose
    every slot has decided is still paused (and still `pending_review`) if
    any of those decisions was a denial. Retained for the tests; production
    code should use `current_stage` / `_stage_is_complete`.
    """
    return not future_course.reviews.filter(
        round=future_course.review_round, decision='',
    ).exists()


def reset_review(future_course):
    """Return the request to `submitted`, unlock it, clear any pause.

    Rows from the finished round keep their round number and are left
    untouched — they are the history. The next `open_review_round` opens
    round N+1.
    """
    future_course.status = 'submitted'
    future_course.review_paused_on = None
    future_course.save(update_fields=['status', 'review_paused_on'])


def is_locked(future_course):
    """True when the school may no longer edit this request."""
    return future_course.status in FutureCourse.LOCKED_STATUSES
