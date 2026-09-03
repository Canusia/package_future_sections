"""CE bulk actions for the review workflow: opening a round and resetting.

`mark_as_pending_review` opens a review round on each selected request via
`open_review_round`, skipping (and naming) any course with no qualifying
reviewer rather than stranding it. `mark_as_submitted` routes through
`reset_review` so the reset semantics live in one place.
"""
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.test import TestCase
from django.urls import reverse

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.teacher import Teacher, TeacherCourseCertificate, TeacherHighSchool
from cis.models.highschool import HighSchool
from cis.models.term import AcademicYear

from ..models import FutureCourse
from ..review.helpers import open_review_round, record_decision


def _user(email):
    return CustomUser.objects.create(username=email, email=email)


def _safe_force_login(client, user):
    # django_login_history's post_login signal handler blows up under the
    # test client (no real REMOTE_ADDR), unrelated to what's under test
    # here. Same workaround used in test_ce_ajax_permission.py.
    from django_login_history.models import post_login
    user_logged_in.disconnect(post_login)
    try:
        client.force_login(user)
    finally:
        user_logged_in.connect(post_login)


class CEReviewActionsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Main', code='M')
        cls.course = Course.objects.create(
            name='A1', title='Alpha', cohort=cls.cohort, catalog_number='101',
            credit_hours=3, campus=cls.campus, status='Active')
        for name in ('ce', 'instructor'):
            Group.objects.get_or_create(name=name)
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
        self.ce_user = CustomUser.objects.create_user(
            username='ce@x.com', email='ce@x.com', password='pw')
        self.ce_user.groups.add(Group.objects.get(name='ce'))

    def _reviewer(self, email, role='Faculty', status='Active'):
        u = _user(email)
        CourseAdministrator.objects.create(
            course=self.course, user=u, role=role, status=status)
        return u

    def test_marking_pending_review_opens_a_round(self):
        self._reviewer('a@x.com')
        _safe_force_login(self.client, self.ce_user)
        resp = self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'mark_as_pending_review', 'ids[]': [str(self.fc.id)]})
        self.assertEqual(resp.json()['status'], 'success')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'pending_review')
        self.assertEqual(self.fc.reviews.filter(round=1).count(), 1)

    def test_a_request_with_no_reviewers_is_reported_not_marked(self):
        _safe_force_login(self.client, self.ce_user)
        resp = self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'mark_as_pending_review', 'ids[]': [str(self.fc.id)]})
        body = resp.json()
        self.assertEqual(body['status'], 'warning')
        self.assertIn('no reviewer', body['message'].lower())
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'submitted')

    def test_a_mixed_batch_marks_the_ones_it_can(self):
        self._reviewer('a@x.com')
        bare_course = Course.objects.create(
            name='B1', title='Bravo', cohort=self.cohort,
            catalog_number='102', credit_hours=3, campus=self.campus,
            status='Active')
        bare_tc = TeacherCourseCertificate.objects.create(
            teacher_highschool=self.tc.teacher_highschool,
            course=bare_course, status='Applicant')
        other = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=bare_tc, status='submitted')

        _safe_force_login(self.client, self.ce_user)
        resp = self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'mark_as_pending_review',
             'ids[]': [str(self.fc.id), str(other.id)]})

        self.fc.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.fc.status, 'pending_review')
        self.assertEqual(other.status, 'submitted')
        self.assertIn('Bravo', resp.json()['message'])

    def test_reselecting_a_pending_review_request_does_not_reopen_a_round(self):
        self._reviewer('a@x.com')
        _safe_force_login(self.client, self.ce_user)
        # Opens round 1.
        self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'mark_as_pending_review', 'ids[]': [str(self.fc.id)]})
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.review_round, 1)
        # Re-selecting the same (still pending_review) request must not
        # open round 2 and orphan round 1's decisions.
        resp = self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'mark_as_pending_review', 'ids[]': [str(self.fc.id)]})
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.review_round, 1)
        self.assertEqual(self.fc.status, 'pending_review')
        self.assertIn('already', resp.json()['message'].lower())

    def test_a_reviewed_request_is_not_reopened(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')
        _safe_force_login(self.client, self.ce_user)
        resp = self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'mark_as_pending_review', 'ids[]': [str(self.fc.id)]})
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.review_round, 1)
        self.assertEqual(self.fc.status, 'reviewed')
        self.assertIn('already', resp.json()['message'].lower())

    def test_mark_as_reviewed_refuses_a_live_pending_review_request(self):
        self._reviewer('a@x.com')
        open_review_round(self.fc)
        _safe_force_login(self.client, self.ce_user)
        resp = self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'mark_as_reviewed', 'ids[]': [str(self.fc.id)]})
        body = resp.json()
        self.assertEqual(body['status'], 'warning')
        self.assertIn('pending review', body['message'].lower())
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'pending_review')

    def test_mark_as_reviewed_still_works_on_a_plain_submitted_request(self):
        _safe_force_login(self.client, self.ce_user)
        resp = self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'mark_as_reviewed', 'ids[]': [str(self.fc.id)]})
        self.assertEqual(resp.json()['status'], 'success')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')

    def test_mark_as_pending_review_is_refused_when_review_disabled(self):
        self._reviewer('a@x.com')
        Setting.objects.filter(key='cis_future_sections').update(
            value={'require_review': 'No', 'reviewer_roles': ['Faculty']})
        _safe_force_login(self.client, self.ce_user)
        resp = self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'mark_as_pending_review', 'ids[]': [str(self.fc.id)]})
        body = resp.json()
        self.assertEqual(body['status'], 'warning')
        self.assertIn('review is not enabled', body['message'].lower())
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'submitted')
        self.assertEqual(self.fc.reviews.count(), 0)

    def test_mark_as_submitted_resets_and_unlocks(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        _safe_force_login(self.client, self.ce_user)
        self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'mark_as_submitted', 'ids[]': [str(self.fc.id)]})
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'submitted')
        self.assertEqual(self.fc.reviews.get(round=1).decision, 'approved')
