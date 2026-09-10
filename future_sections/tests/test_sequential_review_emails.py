"""Who gets told what, and when, under sequential review.

Only the current stage is told it is their turn; a denial tells staff and
nobody else; the cron reminder and CE's per-reviewer chase are both scoped
to the current stage and skip a paused request.
"""
from unittest import mock

from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase, override_settings

from mailer.engine import send_all

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
    open_review_round, record_decision, resume_review,
)

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def _user(email):
    return CustomUser.objects.create(
        username=email, email=email, first_name='F', last_name='L')


def _flush():
    send_all()


BASE = {
    'require_review': '1',
    'reviewer_roles': ['Faculty', 'Dean'],
    'reviewer_role_config': '{"Faculty": 1, "Dean": 2}',
    'review_notification_subject': 'Your turn',
    'review_notification_message':
        'Hi {{reviewer_first_name}}, {{pending_count}} waiting. {{link}}',
    'review_escalation_recipients': 'staff1@x.com, staff2@x.com',
    'review_escalation_subject': 'Section Request Not Approved',
    'review_escalation_message':
        'Denied by {{reviewer_first_name}} ({{reviewer_role}}): {{comment}}',
}


@override_settings(EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
class _EmailFixture(TestCase):

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
        Setting.objects.create(key='cis_future_sections', value=dict(BASE))
        self.fc = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=self.tc, status='submitted')
        mail.outbox = []

    def _reviewer(self, email, role='Faculty'):
        user = _user(email)
        CourseAdministrator.objects.create(
            course=self.course, user=user, role=role, status='Active')
        return user

    def _recipients(self):
        _flush()
        return sorted(addr for m in mail.outbox for addr in m.to)

    def _settle(self):
        """Flush and discard mail queued so far, isolating the next phase.

        django-mailer queues rather than sends: an unflushed message from
        an earlier action in the same test stays pending and would be
        swept up by a later `_flush()`, so each phase boundary must drain
        and clear before the next action queues its own mail.
        """
        _flush()
        mail.outbox = []


class StageNotificationTests(_EmailFixture):

    def test_opening_a_round_notifies_only_the_first_stage(self):
        self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        self.assertEqual(self._recipients(), ['fac@x.com'])

    def test_an_approval_notifies_the_next_stage(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        self._settle()
        record_decision(self.fc, fac, decision='approved')
        self.assertEqual(self._recipients(), ['dean@x.com'])

    def test_every_member_of_a_shared_stage_is_notified(self):
        self._reviewer('fac1@x.com', role='Faculty')
        self._reviewer('fac2@x.com', role='Faculty')
        open_review_round(self.fc)
        self.assertEqual(self._recipients(), ['fac1@x.com', 'fac2@x.com'])

    def test_an_incomplete_stage_notifies_nobody_new(self):
        fac1 = self._reviewer('fac1@x.com', role='Faculty')
        self._reviewer('fac2@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        self._settle()
        record_decision(self.fc, fac1, decision='approved')
        self.assertEqual(self._recipients(), [])

    def test_finishing_the_last_stage_notifies_no_reviewer(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)
        self._settle()
        record_decision(self.fc, fac, decision='approved')
        self.assertEqual(self._recipients(), [])

    def test_a_reviewer_without_an_email_is_skipped_not_fatal(self):
        user = CustomUser.objects.create(username='noemail', email='')
        CourseAdministrator.objects.create(
            course=self.course, user=user, role='Faculty', status='Active')
        self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)
        self.assertEqual(self._recipients(), ['fac@x.com'])


class EscalationTests(_EmailFixture):

    def test_a_denial_emails_the_configured_staff(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        self._settle()
        record_decision(self.fc, fac, decision='not_approved',
                        comment='Enrollment too low')
        self.assertEqual(self._recipients(), ['staff1@x.com', 'staff2@x.com'])

    def test_the_escalation_renders_the_reviewer_and_comment(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)
        self._settle()
        record_decision(self.fc, fac, decision='not_approved',
                        comment='Enrollment too low')
        _flush()
        body = mail.outbox[0].body
        self.assertIn('Faculty', body)
        self.assertIn('Enrollment too low', body)

    def test_a_denial_does_not_notify_the_next_stage(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        self._settle()
        record_decision(self.fc, fac, decision='not_approved')
        self.assertNotIn('dean@x.com', self._recipients())

    def test_no_configured_recipients_sends_nothing_and_still_pauses(self):
        setting = Setting.objects.get(key='cis_future_sections')
        setting.value['review_escalation_recipients'] = ''
        setting.save()
        fac = self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)
        self._settle()
        record_decision(self.fc, fac, decision='not_approved')
        self.assertEqual(self._recipients(), [])
        self.fc.refresh_from_db()
        self.assertTrue(self.fc.is_review_paused)

    def test_resuming_notifies_the_next_stage(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')
        self._settle()
        resume_review(self.fc)
        self.assertEqual(self._recipients(), ['dean@x.com'])


class SendFailureIsolationTests(_EmailFixture):
    """A broken send must never break the reviewed flow it announces.

    Flagged as untested when the notifiers were still stubs (Task 3); now
    that they actually send mail, a real send failure needs to be proven
    non-fatal, not just assumed from the try/except wrapping.
    """

    @mock.patch('mailer.send_html_mail', side_effect=Exception('boom'))
    def test_a_failing_stage_send_does_not_block_advancing(self, _mock):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)

        # The stage-turn email for Dean will raise inside the send -- the
        # approval must still be recorded and the round must still advance.
        row = record_decision(self.fc, fac, decision='approved')

        self.assertEqual(row.decision, 'approved')
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'pending_review')
        from ..review.helpers import current_stage
        self.assertEqual(current_stage(self.fc), 2)

    @mock.patch('mailer.send_html_mail', side_effect=Exception('boom'))
    def test_a_failing_escalation_send_does_not_block_the_pause(self, _mock):
        fac = self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)

        # The escalation email to staff will raise inside the send -- the
        # denial must still be recorded and the request must still pause.
        row = record_decision(self.fc, fac, decision='not_approved',
                               comment='nope')

        self.assertEqual(row.decision, 'not_approved')
        self.fc.refresh_from_db()
        self.assertTrue(self.fc.is_review_paused)


class ReminderScopingTests(_EmailFixture):

    def _cron_settings(self):
        import datetime

        setting = Setting.objects.get(key='cis_future_sections')
        setting.value['review_notification_dates'] = (
            datetime.date.today().strftime('%m/%d/%Y'))
        setting.save()

    def test_the_cron_reminder_only_chases_the_current_stage(self):
        self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        self._cron_settings()
        self._settle()
        FutureCourse.notify_pending_reviews()
        self.assertEqual(self._recipients(), ['fac@x.com'])

    def test_the_cron_reminder_skips_a_paused_request(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')
        self._cron_settings()
        self._settle()
        FutureCourse.notify_pending_reviews()
        self.assertEqual(self._recipients(), [])

    def test_ce_cannot_chase_a_reviewer_outside_the_current_stage(self):
        self._reviewer('fac@x.com', role='Faculty')
        dean = self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        success, message = FutureCourse.send_review_reminder(
            self.fc.id, dean.id)
        self.assertFalse(success)

    def test_ce_can_chase_the_current_stage(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        success, message = FutureCourse.send_review_reminder(
            self.fc.id, fac.id)
        self.assertTrue(success)

    def test_ce_can_still_chase_while_paused(self):
        # The manual gesture is exactly what "controlled manually" means.
        fac1 = self._reviewer('fac1@x.com', role='Faculty')
        fac2 = self._reviewer('fac2@x.com', role='Faculty')
        open_review_round(self.fc)
        record_decision(self.fc, fac1, decision='not_approved')
        success, message = FutureCourse.send_review_reminder(
            self.fc.id, fac2.id)
        self.assertTrue(success)
