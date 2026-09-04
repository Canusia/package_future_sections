"""On-demand per-reviewer reminder send from the CE reviewers modal.

`send_review_reminder` is the "chase this one person about this one
request" gesture: it must never trust the client's choice of recipient.
It re-derives, server-side, that the (future_course, reviewer) pair is an
outstanding slot in the *live* round before sending anything.
"""
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from mailer.engine import send_all
from rest_framework.test import APIClient

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.teacher import Teacher, TeacherCourseCertificate, TeacherHighSchool
from cis.models.highschool import HighSchool
from cis.models.term import AcademicYear

from ..models import FutureCourse
from ..review.helpers import open_review_round, record_decision, reset_review


def _user(email):
    return CustomUser.objects.create(
        username=email, email=email, first_name='F', last_name='L')


def _safe_force_login(client, user):
    # django_login_history's post_login signal handler blows up under the
    # test client (no real REMOTE_ADDR), unrelated to what's under test
    # here. Same workaround used in test_ce_ajax_permission.py and
    # test_ce_review_actions.py.
    from django_login_history.models import post_login
    user_logged_in.disconnect(post_login)
    try:
        client.force_login(user)
    finally:
        user_logged_in.connect(post_login)


LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def _flush():
    """Flush django-mailer's queue into mail.outbox."""
    send_all()


BASE_SETTINGS = {
    'require_review': '1',
    'reviewer_roles': ['Faculty'],
    'review_notification_subject': 'Reminder',
    'review_notification_message':
        'Hi {{reviewer_first_name}}, you have {{pending_count}} pending. '
        '{{requests}} {{link}}',
}


class SendReviewReminderModelTests(TestCase):
    """Tests against `FutureCourse.send_review_reminder` directly."""

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
        Setting.objects.create(key='cis_future_sections', value=dict(BASE_SETTINGS))
        self.fc = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=self.tc, status='submitted')

    def _reviewer(self, email, role='Faculty', status='Active'):
        u = _user(email)
        CourseAdministrator.objects.create(
            course=self.course, user=u, role=role, status=status)
        return u

    def test_reviewer_with_undecided_row_gets_reminder_about_this_request(self):
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)

        success, message = FutureCourse.send_review_reminder(
            self.fc.id, reviewer.id)

        self.assertTrue(success)
        self.assertIn('r@x.com', message)

    def test_submitted_request_is_refused(self):
        reviewer = self._reviewer('r@x.com')
        # fc stays 'submitted' -- no round opened, no review row exists.
        success, message = FutureCourse.send_review_reminder(
            self.fc.id, reviewer.id)
        self.assertFalse(success)

    def test_reviewed_request_is_refused(self):
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, reviewer, decision='approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')

        success, message = FutureCourse.send_review_reminder(
            self.fc.id, reviewer.id)
        self.assertFalse(success)

    def test_reviewer_who_already_decided_is_refused(self):
        a = self._reviewer('a@x.com')
        self._reviewer('b@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        self.fc.refresh_from_db()
        # `b` hasn't decided yet, so the round (and request) is still live
        # -- this isolates the "already decided" refusal from the
        # "round finished" refusal.
        self.assertEqual(self.fc.status, 'pending_review')

        success, message = FutureCourse.send_review_reminder(
            self.fc.id, a.id)
        self.assertFalse(success)

    def test_user_with_no_review_row_is_refused(self):
        """The important case: the client cannot name an arbitrary recipient."""
        self._reviewer('r@x.com')
        open_review_round(self.fc)
        outsider = _user('outsider@x.com')

        success, message = FutureCourse.send_review_reminder(
            self.fc.id, outsider.id)
        self.assertFalse(success)

    def test_malformed_ids_are_refused_not_a_500(self):
        success, message = FutureCourse.send_review_reminder(
            'not-a-uuid', 'also-not-a-uuid')
        self.assertFalse(success)

    @override_settings(DEBUG=True, EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_debug_true_routes_to_testers_not_the_reviewer(self):
        """Django forces DEBUG=False during tests, so exercise the DEBUG
        branch explicitly via override_settings."""
        setting = Setting.objects.get(key='cis_future_sections')
        setting.value['testers'] = 'tester1@x.com, tester2@x.com'
        setting.save()
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)

        success, message = FutureCourse.send_review_reminder(
            self.fc.id, reviewer.id)
        _flush()

        self.assertTrue(success)
        self.assertIn('r@x.com', message)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(sorted(mail.outbox[0].to),
                          ['tester1@x.com', 'tester2@x.com'])
        self.assertNotIn('r@x.com', mail.outbox[0].to)

    @override_settings(DEBUG=True, EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_debug_true_and_blank_testers_fails_clearly_and_sends_nothing(self):
        setting = Setting.objects.get(key='cis_future_sections')
        setting.value['testers'] = ''
        setting.save()
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)

        success, message = FutureCourse.send_review_reminder(
            self.fc.id, reviewer.id)
        _flush()

        self.assertFalse(success)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(DEBUG=False, EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_debug_false_uses_the_real_recipient(self):
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)

        success, message = FutureCourse.send_review_reminder(
            self.fc.id, reviewer.id)
        _flush()

        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['r@x.com'])

    def test_previous_round_row_after_reset_is_refused(self):
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)
        reset_review(self.fc)
        # `reviewer`'s round-1 row is still decision='' but round 1 is no
        # longer the live round.
        success, message = FutureCourse.send_review_reminder(
            self.fc.id, reviewer.id)
        self.assertFalse(success)


class SendReviewReminderViewTests(TestCase):
    """Tests against the `send_review_reminder` CE endpoint."""

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
        cls.hs = HighSchool.objects.create(name='Test HS')
        teacher = Teacher.objects.create(user=_user('t@x.com'))
        ths = TeacherHighSchool.objects.create(
            teacher=teacher, highschool=cls.hs)
        cls.tc = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=cls.course, status='Applicant')

    def setUp(self):
        Setting.objects.create(key='cis_future_sections', value=dict(BASE_SETTINGS))
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

    def test_envelope_matches_other_ce_actions_shape(self):
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)
        _safe_force_login(self.client, self.ce_user)

        resp = self.client.post(
            reverse('future_sections_ce:send_review_reminder'),
            {'future_course_id': str(self.fc.id), 'reviewer_id': str(reviewer.id)})

        body = resp.json()
        self.assertEqual(body['status'], 'success')
        self.assertEqual(body['action'], 'display')
        self.assertIn('title', body)
        self.assertIn('message', body)

    def test_outsider_refused_via_the_endpoint(self):
        self._reviewer('r@x.com')
        open_review_round(self.fc)
        outsider = _user('outsider@x.com')
        _safe_force_login(self.client, self.ce_user)

        resp = self.client.post(
            reverse('future_sections_ce:send_review_reminder'),
            {'future_course_id': str(self.fc.id), 'reviewer_id': str(outsider.id)})

        body = resp.json()
        self.assertEqual(body['status'], 'error')

    def test_requires_ce_role(self):
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)
        non_ce = CustomUser.objects.create_user(
            username='notce@x.com', email='notce@x.com', password='pw')
        _safe_force_login(self.client, non_ce)

        resp = self.client.post(
            reverse('future_sections_ce:send_review_reminder'),
            {'future_course_id': str(self.fc.id), 'reviewer_id': str(reviewer.id)})
        self.assertNotEqual(resp.status_code, 200)

    def test_get_is_rejected_with_405_and_sends_nothing(self):
        """PT-33-style regression: a forged/prefetched GET must not send
        email. Mirrors cis/tests/test_pt33_remove_teaching_status_csrf.py's
        `test_get_does_not_delete_and_returns_405`, adapted for a
        "send mail" state change instead of a delete."""
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)
        _safe_force_login(self.client, self.ce_user)

        resp = self.client.get(
            reverse('future_sections_ce:send_review_reminder'),
            {'future_course_id': str(self.fc.id), 'reviewer_id': str(reviewer.id)})

        self.assertEqual(resp.status_code, 405)

    def test_session_post_without_csrf_token_is_rejected(self):
        """A session-authenticated POST with no CSRF token must be
        rejected, proving CsrfViewMiddleware enforcement (mirrors PT-33's
        `test_session_post_without_csrf_token_is_rejected`)."""
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)
        csrf_client = APIClient(enforce_csrf_checks=True)
        _safe_force_login(csrf_client, self.ce_user)

        resp = csrf_client.post(
            reverse('future_sections_ce:send_review_reminder'),
            {'future_course_id': str(self.fc.id), 'reviewer_id': str(reviewer.id)},
            format='multipart')

        self.assertEqual(resp.status_code, 403)



class CEIndexReviewNotificationHistoryTabTests(TestCase):
    """The Review Notification History tab is gated on `require_review`."""

    @classmethod
    def setUpTestData(cls):
        for name in ('ce', 'instructor'):
            Group.objects.get_or_create(name=name)

    def setUp(self):
        self.ce_user = CustomUser.objects.create_user(
            username='ce@x.com', email='ce@x.com', password='pw')
        self.ce_user.groups.add(Group.objects.get(name='ce'))

    def test_tab_present_when_review_required(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={'require_review': '1', 'reviewer_roles': ['Faculty']})
        _safe_force_login(self.client, self.ce_user)
        resp = self.client.get(reverse('future_sections_ce:future_sections'))
        self.assertContains(resp, 'review_notification_history')
        self.assertContains(resp, 'Review Notification History')

    def test_tab_absent_when_review_not_required(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={'require_review': '2', 'reviewer_roles': ['Faculty']})
        _safe_force_login(self.client, self.ce_user)
        resp = self.client.get(reverse('future_sections_ce:future_sections'))
        self.assertNotContains(resp, 'review_notification_history')
