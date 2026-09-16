"""CE changes to a live review round: skip, delete and add a reviewer.

A skip marks the row `skipped` and keeps it as history. A delete removes an
outstanding or skipped row outright. Either one advances the request through
`advance_or_finish` when it completes the current stage. An add inserts a
row into the live round at the current stage or later.
"""
import json

from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase, override_settings

from mailer.engine import send_all

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.teacher import Teacher, TeacherCourseCertificate, TeacherHighSchool
from cis.models.highschool import HighSchool
from cis.models.term import AcademicYear

from ..models import FutureCourse, SectionRequestReview
from ..review.helpers import (
    NotAReviewerError, ReviewerChangeError, add_reviewer, addable_reviewers,
    current_stage, delete_reviewer, lowest_addable_weight, open_review_round,
    record_decision, skip_reviewer,
)

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def _user(email):
    return CustomUser.objects.create(
        username=email, email=email, first_name='F', last_name=email[0])


class ChangeReviewersBase(TestCase):
    """Faculty (weight 10) → Dept. Chair (20) → Dean (30)."""

    @classmethod
    def setUpTestData(cls):
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Main', code='M')
        cls.course = Course.objects.create(
            name='A1', title='Alpha', cohort=cls.cohort, catalog_number='101',
            credit_hours=3, campus=cls.campus, status='Active')
        Group.objects.get_or_create(name='instructor')
        hs = HighSchool.objects.create(name='Test HS')
        teacher = Teacher.objects.create(user=_user('t@x.com'))
        ths = TeacherHighSchool.objects.create(teacher=teacher, highschool=hs)
        cls.tc = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=cls.course, status='Applicant')

    def setUp(self):
        Setting.objects.create(key='cis_future_sections', value={
            'require_review': '1',
            'reviewer_roles': ['Faculty', 'Dept. Chair', 'Dean'],
            'reviewer_role_config': json.dumps(
                {'Faculty': 10, 'Dept. Chair': 20, 'Dean': 30}),
            'review_notification_subject': 'Your turn',
            'review_notification_message':
                'Hi {{reviewer_first_name}} {{requests}} {{link}}',
        })
        self.fc = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=self.tc, status='submitted')
        self.staff = _user('ce@x.com')

    def _reviewer(self, email, role):
        u = _user(email)
        CourseAdministrator.objects.create(
            course=self.course, user=u, role=role, status='Active')
        return u

    def _row(self, user):
        return SectionRequestReview.objects.get(
            future_course=self.fc, reviewer=user, round=self.fc.review_round)

    def _flush_outbox(self):
        send_all()
        sent = [m.to for m in mail.outbox]
        mail.outbox = []
        return sent


class SkippedDecisionTests(ChangeReviewersBase):

    def test_skipped_is_a_labelled_decision(self):
        self.assertEqual(SectionRequestReview.SKIPPED, 'skipped')
        self.assertEqual(
            dict(SectionRequestReview.DECISION_CHOICES)['skipped'], 'Skipped')

    def test_a_skipped_reviewer_cannot_record_a_decision(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('g@x.com', 'Faculty')
        open_review_round(self.fc)
        row = self._row(faculty)
        row.decision = SectionRequestReview.SKIPPED
        row.skipped_by = self.staff
        row.save()

        with self.assertRaises(NotAReviewerError):
            record_decision(self.fc, faculty, decision='approved')
        self.assertEqual(self._row(faculty).decision, 'skipped')

    def test_a_deleted_reviewer_cannot_record_a_decision(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('g@x.com', 'Faculty')
        open_review_round(self.fc)
        delete_reviewer(self.fc, faculty.pk, by=self.staff)

        with self.assertRaises(NotAReviewerError):
            record_decision(self.fc, faculty, decision='approved')
        self.assertFalse(self.fc.reviews.filter(reviewer=faculty).exists())

    def test_record_decision_rechecks_status_from_the_database(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        open_review_round(self.fc)
        FutureCourse.objects.filter(pk=self.fc.pk).update(status='submitted')

        with self.assertRaises(NotAReviewerError):
            record_decision(self.fc, faculty, decision='approved')
        self.assertEqual(self._row(faculty).decision, '')
        self.assertEqual(self.fc.status, 'submitted')


class SkipReviewerTests(ChangeReviewersBase):

    @override_settings(EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_skipping_the_only_reviewer_in_a_stage_advances_and_notifies_next(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        chair = self._reviewer('c@x.com', 'Dept. Chair')
        self._reviewer('d@x.com', 'Dean')
        open_review_round(self.fc)
        self._flush_outbox()

        skip_reviewer(self.fc, faculty.pk, by=self.staff)

        row = self._row(faculty)
        self.assertEqual(row.decision, 'skipped')
        self.assertEqual(row.skipped_by, self.staff)
        self.assertIsNotNone(row.decided_on)
        self.assertEqual(current_stage(self.fc), 20)
        self.assertEqual(self._flush_outbox(), [[chair.email]])

    @override_settings(EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_skipping_one_of_several_in_a_stage_does_not_advance(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('g@x.com', 'Faculty')
        self._reviewer('c@x.com', 'Dept. Chair')
        open_review_round(self.fc)
        self._flush_outbox()

        skip_reviewer(self.fc, faculty.pk, by=self.staff)

        self.assertEqual(current_stage(self.fc), 10)
        self.assertEqual(self._flush_outbox(), [])

    def test_skipping_the_last_outstanding_reviewer_marks_reviewed(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        chair = self._reviewer('c@x.com', 'Dept. Chair')
        open_review_round(self.fc)
        record_decision(self.fc, faculty, decision='approved')

        skip_reviewer(self.fc, chair.pk, by=self.staff)

        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')

    def test_skipping_a_later_stage_reviewer_does_not_advance(self):
        self._reviewer('f@x.com', 'Faculty')
        chair = self._reviewer('c@x.com', 'Dept. Chair')
        self._reviewer('d@x.com', 'Dean')
        open_review_round(self.fc)

        skip_reviewer(self.fc, chair.pk, by=self.staff)

        self.assertEqual(current_stage(self.fc), 10)

    def test_a_skipped_stage_is_passed_over_when_the_earlier_stage_completes(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        chair = self._reviewer('c@x.com', 'Dept. Chair')
        self._reviewer('d@x.com', 'Dean')
        open_review_round(self.fc)
        skip_reviewer(self.fc, chair.pk, by=self.staff)

        record_decision(self.fc, faculty, decision='approved')

        self.assertEqual(current_stage(self.fc), 30)

    def test_skipping_on_a_paused_request_is_allowed_but_does_not_advance(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        other = self._reviewer('g@x.com', 'Faculty')
        self._reviewer('c@x.com', 'Dept. Chair')
        open_review_round(self.fc)
        record_decision(self.fc, faculty, decision='not_approved')

        skip_reviewer(self.fc, other.pk, by=self.staff)

        self.fc.refresh_from_db()
        self.assertEqual(self._row(other).decision, 'skipped')
        self.assertTrue(self.fc.is_review_paused)
        self.assertEqual(self.fc.status, 'pending_review')

    def test_a_decided_reviewer_cannot_be_skipped(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('g@x.com', 'Faculty')
        open_review_round(self.fc)
        record_decision(self.fc, faculty, decision='approved')

        with self.assertRaises(ReviewerChangeError):
            skip_reviewer(self.fc, faculty.pk, by=self.staff)
        self.assertEqual(self._row(faculty).decision, 'approved')

    def test_a_request_not_under_review_is_refused(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        with self.assertRaises(ReviewerChangeError):
            skip_reviewer(self.fc, faculty.pk, by=self.staff)

    def test_a_malformed_reviewer_id_is_refused_not_raised(self):
        self._reviewer('f@x.com', 'Faculty')
        open_review_round(self.fc)
        with self.assertRaises(ReviewerChangeError):
            skip_reviewer(self.fc, 'not-an-id', by=self.staff)


class DeleteReviewerTests(ChangeReviewersBase):

    def test_deleting_the_only_reviewer_in_a_stage_removes_the_row_and_advances(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('c@x.com', 'Dept. Chair')
        open_review_round(self.fc)

        delete_reviewer(self.fc, faculty.pk, by=self.staff)

        self.assertFalse(self.fc.reviews.filter(reviewer=faculty).exists())
        self.assertEqual(current_stage(self.fc), 20)

    def test_deleting_one_of_several_in_a_stage_does_not_advance(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('g@x.com', 'Faculty')
        open_review_round(self.fc)

        delete_reviewer(self.fc, faculty.pk, by=self.staff)

        self.assertEqual(current_stage(self.fc), 10)

    def test_deleting_the_last_outstanding_reviewer_marks_reviewed(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        open_review_round(self.fc)

        delete_reviewer(self.fc, faculty.pk, by=self.staff)

        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')

    def test_a_skipped_row_can_be_deleted_without_advancing_again(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('g@x.com', 'Faculty')
        open_review_round(self.fc)
        skip_reviewer(self.fc, faculty.pk, by=self.staff)

        delete_reviewer(self.fc, faculty.pk, by=self.staff)

        self.assertFalse(self.fc.reviews.filter(reviewer=faculty).exists())
        self.assertEqual(current_stage(self.fc), 10)

    def test_a_decided_row_cannot_be_deleted(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('g@x.com', 'Faculty')
        open_review_round(self.fc)
        record_decision(self.fc, faculty, decision='approved')

        with self.assertRaises(ReviewerChangeError):
            delete_reviewer(self.fc, faculty.pk, by=self.staff)
        self.assertEqual(self._row(faculty).decision, 'approved')

    def test_a_prior_round_row_is_not_deleted(self):
        from ..review.helpers import reset_review
        faculty = self._reviewer('f@x.com', 'Faculty')
        open_review_round(self.fc)
        reset_review(self.fc)
        open_review_round(self.fc)

        delete_reviewer(self.fc, faculty.pk, by=self.staff)

        self.assertTrue(self.fc.reviews.filter(reviewer=faculty, round=1).exists())

    def test_deleting_on_a_paused_request_is_allowed_and_stays_paused(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        other = self._reviewer('g@x.com', 'Faculty')
        self._reviewer('c@x.com', 'Dept. Chair')
        open_review_round(self.fc)
        record_decision(self.fc, faculty, decision='not_approved')

        delete_reviewer(self.fc, other.pk, by=self.staff)

        self.fc.refresh_from_db()
        self.assertFalse(self.fc.reviews.filter(reviewer=other).exists())
        self.assertTrue(self.fc.is_review_paused)
        self.assertEqual(self.fc.status, 'pending_review')
        self.assertEqual(current_stage(self.fc), 20)


class AddReviewerTests(ChangeReviewersBase):

    def test_addable_excludes_everyone_already_on_the_round(self):
        self._reviewer('f@x.com', 'Faculty')
        open_review_round(self.fc)
        newcomer = self._reviewer('n@x.com', 'Dept. Chair')

        self.assertEqual(
            [(u, r, w) for u, r, w in addable_reviewers(self.fc)],
            [(newcomer, 'Dept. Chair', 20)])

    def test_a_skipped_reviewer_is_not_addable_until_deleted(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('g@x.com', 'Faculty')
        open_review_round(self.fc)
        skip_reviewer(self.fc, faculty.pk, by=self.staff)
        self.assertEqual(addable_reviewers(self.fc), [])

        delete_reviewer(self.fc, faculty.pk, by=self.staff)
        self.assertEqual([t[0] for t in addable_reviewers(self.fc)], [faculty])

    @override_settings(EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_adding_at_the_current_stage_notifies_only_the_newcomer(self):
        self._reviewer('f@x.com', 'Faculty')
        open_review_round(self.fc)
        self._flush_outbox()
        newcomer = self._reviewer('n@x.com', 'Faculty')

        row = add_reviewer(self.fc, newcomer.pk, by=self.staff)

        self.assertEqual((row.round, row.role, row.weight, row.decision),
                         (1, 'Faculty', 10, ''))
        self.assertEqual(self._flush_outbox(), [[newcomer.email]])

    @override_settings(EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_adding_at_a_later_stage_notifies_nobody(self):
        self._reviewer('f@x.com', 'Faculty')
        open_review_round(self.fc)
        self._flush_outbox()
        dean = self._reviewer('d@x.com', 'Dean')

        add_reviewer(self.fc, dean.pk, by=self.staff)

        self.assertEqual(current_stage(self.fc), 10)
        self.assertEqual(self._flush_outbox(), [])

    def test_staff_may_place_the_newcomer_at_a_chosen_later_stage(self):
        self._reviewer('f@x.com', 'Faculty')
        self._reviewer('c@x.com', 'Dept. Chair')
        open_review_round(self.fc)
        dean = self._reviewer('d@x.com', 'Dean')

        row = add_reviewer(self.fc, dean.pk, weight=20, by=self.staff)

        self.assertEqual(row.weight, 20)

    def test_a_closed_stage_is_refused(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('c@x.com', 'Dept. Chair')
        open_review_round(self.fc)
        record_decision(self.fc, faculty, decision='approved')
        newcomer = self._reviewer('n@x.com', 'Faculty')

        self.assertEqual(lowest_addable_weight(self.fc), 20)
        with self.assertRaises(ReviewerChangeError):
            add_reviewer(self.fc, newcomer.pk, by=self.staff)  # weight 10

    def test_someone_who_is_not_a_course_reviewer_is_refused(self):
        self._reviewer('f@x.com', 'Faculty')
        open_review_round(self.fc)
        stranger = _user('s@x.com')

        with self.assertRaises(ReviewerChangeError):
            add_reviewer(self.fc, stranger.pk, by=self.staff)

    @override_settings(EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_adding_to_a_paused_request_is_allowed_and_silent(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('c@x.com', 'Dept. Chair')
        open_review_round(self.fc)
        record_decision(self.fc, faculty, decision='not_approved')
        self._flush_outbox()
        chair2 = self._reviewer('c2@x.com', 'Dept. Chair')

        add_reviewer(self.fc, chair2.pk, by=self.staff)

        self.assertEqual(self._row(chair2).weight, 20)
        self.assertEqual(self._flush_outbox(), [])

    def test_a_request_not_under_review_is_refused(self):
        newcomer = self._reviewer('n@x.com', 'Faculty')
        with self.assertRaises(ReviewerChangeError):
            add_reviewer(self.fc, newcomer.pk, by=self.staff)

    def test_a_request_reviewed_behind_a_stale_instance_is_refused(self):
        self._reviewer('f@x.com', 'Faculty')
        open_review_round(self.fc)
        newcomer = self._reviewer('n@x.com', 'Faculty')
        # Another writer finished the round; self.fc still says pending_review.
        FutureCourse.objects.filter(pk=self.fc.pk).update(status='reviewed')

        with self.assertRaises(ReviewerChangeError):
            add_reviewer(self.fc, newcomer.pk, by=self.staff)
        self.assertFalse(self.fc.reviews.filter(reviewer=newcomer).exists())

    def test_lowest_addable_weight_with_nothing_outstanding_is_the_last_stage(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        chair = self._reviewer('c@x.com', 'Dept. Chair')
        open_review_round(self.fc)
        record_decision(self.fc, faculty, decision='approved')
        record_decision(self.fc, chair, decision='not_approved')

        self.fc.refresh_from_db()
        self.assertTrue(self.fc.is_review_paused)
        self.assertIsNone(current_stage(self.fc))
        self.assertEqual(lowest_addable_weight(self.fc), 20)
