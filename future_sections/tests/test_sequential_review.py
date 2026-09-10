"""Weighted sequential review.

Weight is a *stage*: rows sharing a weight are asked together and the
request advances when all of them have approved. A denial pauses the
request — no further automatic notification — and escalates to staff.
A round whose reviewers all share one weight behaves exactly like the
parallel quorum it replaces.
"""
from django.contrib.auth.models import Group
from django.test import TestCase

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.highschool import HighSchool
from cis.models.settings import Setting
from cis.models.teacher import (
    Teacher, TeacherCourseCertificate, TeacherHighSchool,
)
from cis.models.term import AcademicYear

from ..models import FutureCourse
from ..review.helpers import (
    current_stage, get_reviewer_weights, open_review_round, pending_for,
    qualifying_reviewers, record_decision, reset_review, resume_review,
    stage_rows,
)


def _user(email):
    return CustomUser.objects.create(
        username=email, email=email, first_name='F', last_name='L')


STAGED_SETTINGS = {
    'require_review': '1',
    'reviewer_roles': ['Faculty', 'Dept. Chair', 'Dean'],
    'reviewer_role_config': '{"Faculty": 1, "Dept. Chair": 2, "Dean": 3}',
    'review_notification_subject': 'Your turn',
    'review_notification_message': 'Hi {{reviewer_first_name}} {{link}}',
    'review_escalation_recipients': 'staff@x.com',
    'review_escalation_subject': 'Not approved',
    'review_escalation_message': 'Denied by {{reviewer_first_name}}',
}


class _ReviewFixture:

    @classmethod
    def setUpTestData(cls):
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Main', code='M')
        cls.course = Course.objects.create(
            name='A1', title='Alpha', cohort=cls.cohort, catalog_number='101',
            credit_hours=3, campus=cls.campus, status='Active')
        Group.objects.get_or_create(name='instructor')
        cls.hs = HighSchool.objects.create(name='Test HS')
        teacher = Teacher.objects.create(user=_user('t@x.com'))
        ths = TeacherHighSchool.objects.create(
            teacher=teacher, highschool=cls.hs)
        cls.tc = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=cls.course, status='Applicant')

    def setUp(self):
        Setting.objects.create(
            key='cis_future_sections', value=dict(STAGED_SETTINGS))
        self.fc = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=self.tc, status='submitted')

    def _reviewer(self, email, role='Faculty', status='Active'):
        user = _user(email)
        CourseAdministrator.objects.create(
            course=self.course, user=user, role=role, status=status)
        return user


class ReviewerWeightResolutionTests(_ReviewFixture, TestCase):

    def test_weights_come_from_the_config(self):
        self.assertEqual(
            get_reviewer_weights(),
            {'Faculty': 1, 'Dept. Chair': 2, 'Dean': 3})

    def test_a_role_missing_from_the_config_defaults_to_zero(self):
        setting = Setting.objects.get(key='cis_future_sections')
        setting.value['reviewer_role_config'] = '{"Dean": 3}'
        setting.save()
        self.assertEqual(get_reviewer_weights()['Faculty'], 0)

    def test_no_config_puts_every_role_in_one_stage(self):
        setting = Setting.objects.get(key='cis_future_sections')
        setting.value['reviewer_role_config'] = ''
        setting.save()
        self.assertEqual(set(get_reviewer_weights().values()), {0})

    def test_qualifying_reviewers_carry_their_weight_sorted(self):
        self._reviewer('dean@x.com', role='Dean')
        self._reviewer('fac@x.com', role='Faculty')
        pairs = qualifying_reviewers(self.fc)
        self.assertEqual([w for _u, _r, w in pairs], [1, 3])
        self.assertEqual([r for _u, r, _w in pairs], ['Faculty', 'Dean'])

    def test_a_user_holding_two_roles_is_asked_once_at_the_lower_weight(self):
        user = self._reviewer('both@x.com', role='Dean')
        CourseAdministrator.objects.create(
            course=self.course, user=user, role='Faculty', status='Active')
        pairs = qualifying_reviewers(self.fc)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][1], 'Faculty')
        self.assertEqual(pairs[0][2], 1)


class StageSnapshotTests(_ReviewFixture, TestCase):

    def test_opening_a_round_stores_each_row_weight(self):
        self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        by_email = {
            r.reviewer.email: r.weight for r in self.fc.reviews.all()}
        self.assertEqual(by_email, {'fac@x.com': 1, 'dean@x.com': 3})

    def test_current_stage_is_the_lowest_undecided_weight(self):
        self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        self.assertEqual(current_stage(self.fc), 1)

    def test_stage_rows_returns_only_that_stage(self):
        self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        emails = {r.reviewer.email for r in stage_rows(self.fc)}
        self.assertEqual(emails, {'fac@x.com'})

    def test_two_reviewers_at_one_weight_are_one_stage(self):
        self._reviewer('fac1@x.com', role='Faculty')
        self._reviewer('fac2@x.com', role='Faculty')
        open_review_round(self.fc)
        self.assertEqual(stage_rows(self.fc).count(), 2)

    def test_current_stage_is_none_when_nothing_is_outstanding(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='approved')
        self.assertIsNone(current_stage(self.fc))


class StageAdvanceTests(_ReviewFixture, TestCase):

    def test_an_approval_advances_to_the_next_stage(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='approved')
        self.assertEqual(current_stage(self.fc), 3)
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'pending_review')

    def test_a_stage_does_not_advance_until_all_its_members_decide(self):
        fac1 = self._reviewer('fac1@x.com', role='Faculty')
        self._reviewer('fac2@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac1, decision='approved')
        self.assertEqual(current_stage(self.fc), 1)

    def test_approving_the_last_stage_marks_the_request_reviewed(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        dean = self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='approved')
        record_decision(self.fc, dean, decision='approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')
        self.assertFalse(self.fc.is_review_paused)

    def test_a_single_weight_round_behaves_like_the_old_quorum(self):
        setting = Setting.objects.get(key='cis_future_sections')
        setting.value['reviewer_role_config'] = (
            '{"Faculty": 1, "Dept. Chair": 1, "Dean": 1}')
        setting.save()
        fac = self._reviewer('fac@x.com', role='Faculty')
        dean = self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        self.assertEqual(stage_rows(self.fc).count(), 2)
        record_decision(self.fc, fac, decision='approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'pending_review')
        record_decision(self.fc, dean, decision='approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')


class DenialPausesTests(_ReviewFixture, TestCase):

    def test_a_denial_pauses_the_request(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')
        self.fc.refresh_from_db()
        self.assertTrue(self.fc.is_review_paused)
        self.assertEqual(self.fc.status, 'pending_review')

    def test_a_denial_does_not_advance_the_stage(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')
        # The Dean's row is untouched and nobody was notified; CE decides.
        self.assertEqual(
            self.fc.reviews.get(role='Dean').decision, '')

    def test_a_denial_in_the_last_stage_does_not_mark_it_reviewed(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'pending_review')
        self.assertTrue(self.fc.is_review_paused)

    def test_a_denial_pauses_even_with_a_stage_peer_undecided(self):
        fac1 = self._reviewer('fac1@x.com', role='Faculty')
        self._reviewer('fac2@x.com', role='Faculty')
        open_review_round(self.fc)
        record_decision(self.fc, fac1, decision='not_approved')
        self.fc.refresh_from_db()
        self.assertTrue(self.fc.is_review_paused)


class ResumeTests(_ReviewFixture, TestCase):

    def test_resuming_clears_the_pause_and_opens_the_next_stage(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')

        self.assertEqual(resume_review(self.fc), 3)
        self.fc.refresh_from_db()
        self.assertFalse(self.fc.is_review_paused)
        self.assertEqual(self.fc.status, 'pending_review')

    def test_the_denial_stays_on_the_record_after_resuming(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')
        resume_review(self.fc)
        self.assertEqual(
            self.fc.reviews.get(reviewer=fac).decision, 'not_approved')

    def test_resuming_with_nothing_outstanding_marks_it_reviewed(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')

        self.assertIsNone(resume_review(self.fc))
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')
        self.assertFalse(self.fc.is_review_paused)

    def test_reset_clears_the_pause_too(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')
        reset_review(self.fc)
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'submitted')
        self.assertFalse(self.fc.is_review_paused)


class PendingQueueScopingTests(_ReviewFixture, TestCase):

    def test_only_the_current_stage_sees_it_as_pending(self):
        self._reviewer('fac@x.com', role='Faculty')
        dean = self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        self.assertNotIn(self.fc, pending_for(dean))

    def test_the_current_stage_sees_it_as_pending(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)
        self.assertIn(self.fc, pending_for(fac))

    def test_the_next_stage_sees_it_once_its_turn_comes(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        dean = self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='approved')
        self.assertIn(self.fc, pending_for(dean))

    def test_a_paused_request_is_in_nobody_s_pending_queue(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')
        for user in (fac, self.fc.reviews.get(role='Dean').reviewer):
            self.assertNotIn(self.fc, pending_for(user))
