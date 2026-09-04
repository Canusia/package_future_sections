from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase, override_settings
from datetime import date

from mailer.engine import send_all

from cis.models.customuser import CustomUser
from cis.models.course import Course, Cohort
from cis.models.term import AcademicYear, Term
from cis.models.highschool import HighSchool
from cis.models.district import District
from cis.models.teacher import (
    Teacher, TeacherHighSchool, TeacherCourseCertificate,
)
from cis.models.section import ClassSection
from cis.models.settings import Setting
from cis.models.highschool_administrator import (
    HSAdministrator, HSAdministratorPosition, HSPosition,
)

from ..models import FutureCourse

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def _flush():
    """Flush django-mailer's queue into mail.outbox."""
    send_all()


class NotifyPendingLookbackTests(TestCase):
    def _world(self):
        Group.objects.get_or_create(name='instructor')
        Group.objects.get_or_create(name='faculty')
        Group.objects.get_or_create(name='highschool_admin')

        ay = AcademicYear.objects.create(name='2026-2027')
        fall = Term.objects.create(
            code='FA26', label='Fall 2026', academic_year=ay,
        )
        lb_ay = AcademicYear.objects.create(name='2025-2026')
        lb_fall = Term.objects.create(
            code='FA25', label='Fall 2025', academic_year=lb_ay,
        )

        cohort = Cohort.objects.create(designator='ENG', name='English')
        course = Course.objects.create(
            cohort=cohort, catalog_number='101', title='Comp I',
            name='ENG 101', credit_hours=3, status='Active',
        )
        district = District.objects.create(name='D')
        hs = HighSchool.objects.create(name='HS', district=district)

        user = CustomUser.objects.create(
            username='t@x.com', email='t@x.com',
            first_name='T', last_name='X')
        teacher = Teacher.objects.create(user=user)
        ths = TeacherHighSchool.objects.create(teacher=teacher, highschool=hs)
        cert = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=course, status='Teaching')

        # Active section in lookback term for this teacher x course
        ClassSection.objects.create(
            teacher=teacher, course=course, term=lb_fall, highschool=hs,
            status='A', section_number='001', class_number=1001,
            start_date='2025-09-01', end_date='2025-12-15',
        )

        # HS admin
        admin_user = CustomUser.objects.create(
            username='admin@x.com', email='admin@x.com',
            first_name='A', last_name='Dmin')
        hsadmin = HSAdministrator.objects.create(user=admin_user)
        position = HSPosition.objects.create(name='Principal')
        HSAdministratorPosition.objects.create(
            hsadmin=hsadmin, highschool=hs,
            position=position, status='active')

        Setting.objects.create(
            key='cis_future_sections',
            value={
                'academic_year': str(ay.id),
                'cycle_terms': [str(fall.id)],
                'lookback_terms': [str(lb_fall.id)],
                'teacher_course_status': ['Teaching'],
                'course_status': ['Active'],
                'allow_new_teacher_create': '2',
                'pending_notification_dates': date.today().strftime('%m/%d/%Y'),
                'pending_notification_message':
                    'Hi {{admin_first_name}}, {{highschool}} is missing '
                    '{{pending_count}} response(s) for {{missing_terms}}.',
                'pending_notification_subject': 'Reminder',
                'pending_notification_roles': [str(position.id)],
            },
        )
        return {'hs': hs, 'cert': cert, 'teacher': teacher,
                'lb_fall': lb_fall, 'fall': fall, 'admin_user': admin_user}

    def test_pending_uses_lookback_universe(self):
        self._world()
        summary, log = FutureCourse.notify_pending_section_requests()
        self.assertEqual(len(log['emails_sent']), 1)

    def test_no_email_when_school_has_responded(self):
        w = self._world()
        ay = w['fall'].academic_year
        FutureCourse.objects.create(
            teacher_course=w['cert'],
            academic_year=ay,
            section_info={'teaching': 'yes',
                          'sections': [{'term': str(w['fall'].id)}]},
        )
        summary, log = FutureCourse.notify_pending_section_requests()
        self.assertEqual(len(log['emails_sent']), 0)

    def _set_settings(self, **overrides):
        from cis.models.settings import Setting
        setting = Setting.objects.get(key='cis_future_sections')
        setting.value.update(overrides)
        setting.save()

    @override_settings(DEBUG=True, EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_debug_true_routes_to_testers_not_the_admin(self):
        """Django forces DEBUG=False during tests, so exercise the DEBUG
        branch explicitly via override_settings."""
        self._world()
        self._set_settings(testers='tester1@x.com, tester2@x.com')

        summary, log = FutureCourse.notify_pending_section_requests()
        _flush()

        self.assertEqual(len(log['emails_sent']), 1)
        # Audit trail still names the real intended recipient...
        self.assertEqual(log['emails_sent'][0]['email'], 'admin@x.com')
        # ...but the mail itself went to the tenant's configured testers.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(sorted(mail.outbox[0].to),
                          ['tester1@x.com', 'tester2@x.com'])
        self.assertNotIn('admin@x.com', mail.outbox[0].to)

    @override_settings(DEBUG=True, EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_debug_true_and_blank_testers_sends_nothing_and_is_skipped(self):
        self._world()
        self._set_settings(testers='')

        summary, log = FutureCourse.notify_pending_section_requests()
        _flush()

        self.assertEqual(len(log['emails_sent']), 0)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(log['skipped'],
                         'Blank testers under DEBUG must be recorded as skipped.')

    @override_settings(DEBUG=False, EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
    def test_debug_false_uses_the_real_recipient(self):
        self._world()

        summary, log = FutureCourse.notify_pending_section_requests()
        _flush()

        self.assertEqual(len(log['emails_sent']), 1)
        self.assertEqual(log['emails_sent'][0]['email'], 'admin@x.com')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin@x.com'])
