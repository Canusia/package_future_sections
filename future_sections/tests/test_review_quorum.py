import json

from django.contrib.auth.models import Group
from django.test import TestCase

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.teacher import Teacher, TeacherCourseCertificate, TeacherHighSchool
from cis.models.highschool import HighSchool
from cis.models.term import AcademicYear

from ..models import FutureCourse, SectionRequestReview
from ..review.helpers import (
    NoReviewersError, NotAReviewerError, is_locked, open_review_round,
    qualifying_reviewers, record_decision, reset_review, round_is_complete,
)


def _user(email):
    return CustomUser.objects.create(username=email, email=email)


class QuorumTests(TestCase):

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
        Setting.objects.create(
            key='cis_future_sections',
            value={'require_review': '1', 'reviewer_roles': ['Faculty']})
        self.fc = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=self.tc, status='submitted')

    def _reviewer(self, email, role='Faculty', status='Active'):
        u = _user(email)
        CourseAdministrator.objects.create(
            course=self.course, user=u, role=role, status=status)
        return u

    # -- snapshot --------------------------------------------------------

    def test_qualifying_reviewers_are_active_rows_in_configured_roles(self):
        wanted = self._reviewer('a@x.com')
        self._reviewer('b@x.com', role='Dean')
        self._reviewer('c@x.com', status='Inactive')
        self.assertEqual(
            [u for u, _role in qualifying_reviewers(self.fc)], [wanted])

    def test_opening_a_round_creates_one_row_per_reviewer(self):
        self._reviewer('a@x.com')
        self._reviewer('d@x.com')
        open_review_round(self.fc)
        self.assertEqual(self.fc.reviews.filter(round=1).count(), 2)
        self.assertEqual(
            list(self.fc.reviews.values_list('decision', flat=True)), ['', ''])

    def test_opening_a_round_records_the_qualifying_role(self):
        self._reviewer('a@x.com')
        open_review_round(self.fc)
        self.assertEqual(self.fc.reviews.get().role, 'Faculty')

    def test_opening_a_round_sets_status_and_round(self):
        self._reviewer('a@x.com')
        self.assertEqual(open_review_round(self.fc), 1)
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'pending_review')
        self.assertEqual(self.fc.review_round, 1)

    def test_a_course_with_no_reviewers_is_refused(self):
        with self.assertRaises(NoReviewersError):
            open_review_round(self.fc)
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'submitted')

    # -- quorum ----------------------------------------------------------

    def test_round_is_incomplete_while_anyone_is_undecided(self):
        a = self._reviewer('a@x.com')
        self._reviewer('d@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        self.assertFalse(round_is_complete(self.fc))
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'pending_review')

    def test_last_decision_completes_the_round_and_advances(self):
        a = self._reviewer('a@x.com')
        d = self._reviewer('d@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        record_decision(self.fc, d, decision='not_approved')
        self.assertTrue(round_is_complete(self.fc))
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')

    def test_a_decision_records_comment_and_timestamp(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        row = record_decision(self.fc, a, decision='approved', comment='ok')
        self.assertEqual(row.decision, 'approved')
        self.assertEqual(row.comment, 'ok')
        self.assertIsNotNone(row.decided_on)

    def test_a_non_snapshot_user_cannot_decide(self):
        self._reviewer('a@x.com')
        open_review_round(self.fc)
        latecomer = self._reviewer('late@x.com')
        with self.assertRaises(NotAReviewerError):
            record_decision(self.fc, latecomer, decision='approved')

    def test_a_reviewer_deactivated_mid_round_can_still_decide(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        CourseAdministrator.objects.filter(user=a).update(status='Inactive')
        record_decision(self.fc, a, decision='approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')

    def test_a_reviewer_may_change_their_decision(self):
        # Two reviewers so the round is still live (one slot undecided)
        # after `a` posts their first decision -- this exercises "change
        # within a live round", not a post-completion rewrite.
        a = self._reviewer('a@x.com')
        self._reviewer('d@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        record_decision(self.fc, a, decision='not_approved')
        self.assertEqual(
            self.fc.reviews.get(reviewer=a).decision, 'not_approved')
        self.assertEqual(self.fc.reviews.count(), 2)
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'pending_review')

    def test_a_decision_cannot_be_posted_after_reset(self):
        a = self._reviewer('a@x.com')
        b = self._reviewer('d@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        reset_review(self.fc)
        with self.assertRaises(NotAReviewerError):
            record_decision(self.fc, b, decision='approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'submitted')
        self.assertEqual(self.fc.reviews.get(round=1, reviewer=b).decision, '')

    def test_a_decision_cannot_be_posted_on_a_reviewed_request(self):
        a = self._reviewer('a@x.com')
        d = self._reviewer('d@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        record_decision(self.fc, d, decision='not_approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')
        with self.assertRaises(NotAReviewerError):
            record_decision(self.fc, a, decision='not_approved')

    # -- reset -----------------------------------------------------------

    def test_reset_unlocks_and_returns_to_submitted(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        reset_review(self.fc)
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'submitted')
        self.assertFalse(is_locked(self.fc))

    def test_reset_retains_the_finished_round(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved', comment='first pass')
        reset_review(self.fc)
        row = self.fc.reviews.get(round=1)
        self.assertEqual(row.decision, 'approved')
        self.assertEqual(row.comment, 'first pass')

    def test_the_next_round_opens_fresh_at_n_plus_one(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        reset_review(self.fc)
        self.assertEqual(open_review_round(self.fc), 2)
        self.assertEqual(self.fc.reviews.get(round=2).decision, '')
        self.assertEqual(self.fc.reviews.count(), 2)

    # -- lock ------------------------------------------------------------

    def test_submitted_is_not_locked(self):
        self.assertFalse(is_locked(self.fc))

    def test_pending_review_and_reviewed_are_locked(self):
        for status in ('pending_review', 'reviewed'):
            self.fc.status = status
            self.assertTrue(is_locked(self.fc), status)
