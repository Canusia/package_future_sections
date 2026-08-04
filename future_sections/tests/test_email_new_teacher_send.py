import json

from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from mailer.engine import send_all

from cis.models.customuser import CustomUser
from cis.models.course import Course, Cohort
from cis.models.district import District
from cis.models.highschool import HighSchool
from cis.models.settings import Setting
from cis.models.teacher import (
    Teacher, TeacherHighSchool, TeacherCourseCertificate,
)
from cis.models.term import AcademicYear

from future_sections.future_sections.models import FutureCourse

# django-mailer's send_html_mail() queues an outgoing message rather than
# delivering it; both Django's own mail and django-mailer's delivery engine
# must point at locmem for send_all() to land in mail.outbox. Same pattern
# as support_ticket/tests/test_signals.py.
LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def _flush():
    """Flush django-mailer's queue into mail.outbox."""
    send_all()


def _safe_force_login(client, user):
    # django_login_history's post_login signal handler blows up under the
    # test client (no real REMOTE_ADDR), unrelated to what's under test
    # here. Same workaround used in test_review_views.py and
    # test_ce_ajax_permission.py.
    from django_login_history.models import post_login
    user_logged_in.disconnect(post_login)
    try:
        client.force_login(user)
    finally:
        user_logged_in.connect(post_login)


class _Base(TestCase):
    def setUp(self):
        for name in ('ce', 'instructor', 'faculty', 'applicant'):
            Group.objects.get_or_create(name=name)

        self.ay = AcademicYear.objects.create(name='2027-2028')
        cohort = Cohort.objects.create(designator='HI', name='History')
        self.course = Course.objects.create(
            cohort=cohort, catalog_number='111', title='History 111',
            name='HIST 111', credit_hours=3, status='Active')
        district = District.objects.create(name='D')
        self.hs = HighSchool.objects.create(name='Zillah High', district=district)

        tuser = CustomUser.objects.create(
            username='t@x.com', email='t@x.com',
            first_name='Brock', last_name='Anderson')
        teacher = Teacher.objects.create(user=tuser)
        ths = TeacherHighSchool.objects.create(
            teacher=teacher, highschool=self.hs)
        cert = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=self.course, status='Teaching')

        self.fc = FutureCourse.objects.create(
            teacher_course=cert, academic_year=self.ay,
            section_info={'teaching': 'yes', 'sections': [{
                'teacher_changed': 'yes',
                'term_name': 'Fall 2027',
                'new_teacher_name': 'Jane Roe',
                'new_teacher_email': 'jane@zillah.test',
            }]},
        )

        Setting.objects.update_or_create(
            key='cis_future_sections',
            defaults={'value': {'academic_year': str(self.ay.id)}})

        self.ce = CustomUser.objects.create_user(
            username='ce@x.com', email='ce@x.com', password='pw')
        self.ce.groups.add(Group.objects.get(name='ce'))
        _safe_force_login(self.client, self.ce)
        self.url = reverse('future_sections_ce:future_sections_actions')

    def _post(self, **overrides):
        data = {
            'action': 'email-new-teacher',
            'future_course_id': str(self.fc.id),
            'section_index': 0,
            'recipient': 'jane@zillah.test',
            'subject': 'Invitation',
            'message': 'Hello {{new_teacher_name}} — apply here: {{link}}',
            'mode': 'start_app',
            'confirm_recipient': 'on',
        }
        data.update(overrides)
        return self.client.post(self.url, data)


class ComposeRenderTests(_Base):
    def test_get_returns_the_compose_box_prefilled(self):
        response = self.client.get(self.url, {
            'action': 'email-new-teacher',
            'future_course_id': str(self.fc.id),
            'section_index': 0,
        })
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('jane@zillah.test', body)
        self.assertIn('confirm_recipient', body)


@override_settings(EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
class StartAppSendTests(_Base):
    def test_sends_one_email_to_the_recipient(self):
        self._post()
        _flush()
        self.assertEqual(len(mail.outbox), 1)

    def test_shortcodes_are_rendered(self):
        self._post()
        _flush()
        body = mail.outbox[0].body + str(mail.outbox[0].alternatives)
        self.assertIn('Jane Roe', body)
        self.assertNotIn('{{new_teacher_name}}', body)
        self.assertNotIn('{{link}}', body)

    def test_a_history_entry_is_recorded(self):
        self._post()
        self.fc.refresh_from_db()
        history = (self.fc.meta or {}).get('history', [])
        self.assertTrue(any('jane@zillah.test' in e['action']
                            for e in history), history)

    def test_nothing_is_created_in_start_app_mode(self):
        before = CustomUser.objects.count()
        self._post()
        self.assertEqual(CustomUser.objects.count(), before)

    def test_missing_confirmation_sends_nothing(self):
        response = self._post(confirm_recipient='')
        _flush()
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotEqual(response.status_code, 500)

    def test_section_not_marked_changed_sends_nothing(self):
        self.fc.section_info['sections'][0]['teacher_changed'] = 'no'
        self.fc.save()
        self._post()
        _flush()
        self.assertEqual(len(mail.outbox), 0)

    def test_non_ce_user_cannot_send(self):
        self.client.logout()
        other = CustomUser.objects.create_user(
            username='i@x.com', email='i@x.com', password='pw')
        other.groups.add(Group.objects.get(name='instructor'))
        _safe_force_login(self.client, other)
        self._post()
        _flush()
        self.assertEqual(len(mail.outbox), 0)
