from datetime import date

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

from ..models import FutureCourse
from ..review.helpers import open_review_round, record_decision, reset_review


def _user(email):
    return CustomUser.objects.create(
        username=email, email=email, first_name='F', last_name='L')


TODAY = date.today().strftime('%m/%d/%Y')
LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def _flush():
    """Flush django-mailer's queue into mail.outbox."""
    send_all()

BASE_SETTINGS = {
    'require_review': '1',
    'reviewer_roles': ['Faculty'],
    'review_notification_dates': TODAY,
    'review_notification_subject': 'Reminder',
    'review_notification_message':
        'Hi {{reviewer_first_name}}, you have {{pending_count}} pending. '
        '{{requests}} {{link}}',
}


class NotifyPendingReviewsTests(TestCase):

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

    def _set_settings(self, **overrides):
        setting = Setting.objects.get(key='cis_future_sections')
        setting.value.update(overrides)
        setting.save()

    def test_nothing_sends_when_review_not_required(self):
        self._set_settings(require_review='2')
        reviewer = self._reviewer('r@x.com')
        # Need review_required() True to open a round in the first place,
        # so open it before flipping the setting off.
        self._set_settings(require_review='1')
        open_review_round(self.fc)
        self._set_settings(require_review='2')

        summary, log = FutureCourse.notify_pending_reviews()
        self.assertEqual(len(log['emails_sent']), 0)

    def test_nothing_sends_when_today_is_not_a_configured_date(self):
        self._reviewer('r@x.com')
        open_review_round(self.fc)
        self._set_settings(review_notification_dates='01/01/1999')

        summary, log = FutureCourse.notify_pending_reviews()
        self.assertEqual(len(log['emails_sent']), 0)

    def test_reviewer_with_undecided_row_gets_one_email_listing_all(self):
        course2 = Course.objects.create(
            name='B1', title='Beta', cohort=self.cohort, catalog_number='102',
            credit_hours=3, campus=self.campus, status='Active')
        tc2 = TeacherCourseCertificate.objects.create(
            teacher_highschool=self.tc.teacher_highschool, course=course2,
            status='Applicant')
        fc2 = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=tc2, status='submitted')

        reviewer = self._reviewer('r@x.com')
        CourseAdministrator.objects.create(
            course=course2, user=reviewer, role='Faculty', status='Active')

        open_review_round(self.fc)
        open_review_round(fc2)

        summary, log = FutureCourse.notify_pending_reviews()
        self.assertEqual(len(log['emails_sent']), 1)
        self.assertEqual(log['emails_sent'][0]['pending_count'], 2)

    def test_reviewer_who_decided_gets_nothing(self):
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, reviewer, decision='approved')

        summary, log = FutureCourse.notify_pending_reviews()
        self.assertEqual(len(log['emails_sent']), 0)

    def test_submitted_status_contributes_nothing(self):
        self._reviewer('r@x.com')
        # fc stays 'submitted' -- no round opened.
        summary, log = FutureCourse.notify_pending_reviews()
        self.assertEqual(len(log['emails_sent']), 0)

    def test_reviewed_status_contributes_nothing(self):
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, reviewer, decision='approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')

        summary, log = FutureCourse.notify_pending_reviews()
        self.assertEqual(len(log['emails_sent']), 0)

    def test_previous_round_undecided_row_not_resurfaced_after_reset(self):
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)
        reset_review(self.fc)

        # Round 1 row for `reviewer` is still decision='' but is history now
        # since round_required for round 1 no longer matches review_round.
        summary, log = FutureCourse.notify_pending_reviews()
        self.assertEqual(len(log['emails_sent']), 0)

    @override_settings(DEBUG=True, EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_debug_true_routes_to_testers_not_the_reviewer(self):
        """Django forces DEBUG=False during tests, so exercise the DEBUG
        branch explicitly via override_settings."""
        self._set_settings(testers='tester1@x.com, tester2@x.com')
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)

        summary, log = FutureCourse.notify_pending_reviews()
        _flush()

        self.assertEqual(len(log['emails_sent']), 1)
        # Audit trail still names the real intended recipient...
        self.assertEqual(log['emails_sent'][0]['email'], 'r@x.com')
        # ...but the mail itself went to the tenant's configured testers.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(sorted(mail.outbox[0].to),
                          ['tester1@x.com', 'tester2@x.com'])
        self.assertNotIn('r@x.com', mail.outbox[0].to)

    @override_settings(DEBUG=True, EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_debug_true_and_blank_testers_sends_nothing_and_is_skipped(self):
        self._set_settings(testers='')
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)

        summary, log = FutureCourse.notify_pending_reviews()
        _flush()

        self.assertEqual(len(log['emails_sent']), 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(log['skipped'],
                         'Blank testers under DEBUG must be recorded as skipped.')

    @override_settings(DEBUG=False, EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_debug_false_uses_the_real_recipient(self):
        reviewer = self._reviewer('r@x.com')
        open_review_round(self.fc)

        summary, log = FutureCourse.notify_pending_reviews()
        _flush()

        self.assertEqual(len(log['emails_sent']), 1)
        self.assertEqual(log['emails_sent'][0]['email'], 'r@x.com')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['r@x.com'])
