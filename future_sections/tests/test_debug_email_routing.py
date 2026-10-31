"""DEBUG mail goes to the tenant's `testers`, never a hardcoded address (#8).

With DEBUG on and no testers configured, nothing is sent.
"""
import os
import re
from unittest import mock

from django.contrib.auth.models import Group
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from cis.models.course import Cohort, Course
from cis.models.customuser import CustomUser
from cis.models.highschool import HighSchool
from cis.models.highschool_administrator import (
    HSAdministrator, HSAdministratorPosition, HSPosition)
from cis.models.settings import Setting
from cis.models.teacher import (
    Teacher, TeacherCourseCertificate, TeacherHighSchool)
from cis.models.term import AcademicYear

from . import PKG
from ..models import FutureCourse
from .test_email_new_teacher_send import _safe_force_login

PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REVIEWED = {
    'send_reviewed_notification': 'Yes',
    'reviewed_email_subject': 'Reviewed',
    'reviewed_email_message': 'Hi {{instructor_first_name}}',
}


class _Base(TestCase):
    def setUp(self):
        for name in ('ce', 'instructor', 'highschool_admin'):
            Group.objects.get_or_create(name=name)
        self.ay = AcademicYear.objects.create(name='2027-2028')
        cohort = Cohort.objects.create(designator='HI', name='History')
        course = Course.objects.create(
            cohort=cohort, catalog_number='111', title='History 111',
            name='HIST 111', credit_hours=3, status='Active')
        self.hs = HighSchool.objects.create(name='Zillah High')
        tuser = CustomUser.objects.create(
            username='t@x.com', email='teacher@zillah.test', first_name='Brock')
        ths = TeacherHighSchool.objects.create(
            teacher=Teacher.objects.create(user=tuser), highschool=self.hs)
        cert = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=course, status='Teaching')
        self.fc = FutureCourse.objects.create(
            teacher_course=cert, academic_year=self.ay,
            section_info={'teaching': 'yes', 'sections': [{
                'teacher_changed': 'yes', 'term_name': 'Fall 2027',
                'new_teacher_name': 'Jane Roe',
                'new_teacher_email': 'jane@zillah.test'}]},
            meta={'submitted_by': {'email': 'admin@zillah.test'}})

    def _config(self, **extra):
        value = {'academic_year': str(self.ay.id), **extra}
        Setting.objects.update_or_create(
            key='cis_future_sections', defaults={'value': value})

    def _sent_to(self, send):
        return [addr for c in send.call_args_list for addr in c.args[4]]


class ReviewedSignalTests(_Base):
    def _review(self):
        with mock.patch(f'{PKG}.signals.send_html_mail') as send:
            self.fc.status = 'reviewed'
            self.fc.save()
        return send

    @override_settings(DEBUG=True)
    def test_debug_without_testers_sends_nothing(self):
        self._config(testers='', **REVIEWED)
        self.assertFalse(self._review().called)

    @override_settings(DEBUG=True)
    def test_debug_sends_once_to_testers(self):
        self._config(testers='qa@tenant.test, lead@tenant.test', **REVIEWED)
        send = self._review()
        self.assertEqual(send.call_count, 1)
        self.assertEqual(sorted(self._sent_to(send)),
                         ['lead@tenant.test', 'qa@tenant.test'])

    @override_settings(DEBUG=False)
    def test_production_sends_to_teacher_and_submitter(self):
        self._config(testers='qa@tenant.test', **REVIEWED)
        send = self._review()
        self.assertEqual(sorted(self._sent_to(send)),
                         ['admin@zillah.test', 'teacher@zillah.test'])


class EmailNewTeacherTests(_Base):
    def setUp(self):
        super().setUp()
        self.ce = CustomUser.objects.create_user(
            username='ce@x.com', email='ce@x.com', password='pw')
        self.ce.groups.add(Group.objects.get(name='ce'))
        _safe_force_login(self.client, self.ce)

    def _post(self):
        # email_new_teacher imports send_html_mail locally.
        with mock.patch('mailer.send_html_mail') as send:
            response = self.client.post(
                reverse('future_sections_ce:future_sections_actions'), {
                    'action': 'email-new-teacher',
                    'future_course_id': str(self.fc.id),
                    'section_index': 0, 'recipient': 'jane@zillah.test',
                    'subject': 'Invitation', 'message': 'Hello',
                    'mode': 'start_app', 'confirm_recipient': 'on'})
        return response, send

    @override_settings(DEBUG=True)
    def test_debug_without_testers_sends_nothing(self):
        self._config(testers='')
        response, send = self._post()
        self.assertFalse(send.called)
        self.assertEqual(response.status_code, 400)

    @override_settings(DEBUG=True)
    def test_debug_routes_to_testers(self):
        self._config(testers='qa@tenant.test')
        _response, send = self._post()
        self.assertEqual(self._sent_to(send), ['qa@tenant.test'])


class PendingReminderTests(_Base):
    def setUp(self):
        super().setUp()
        admin_user = CustomUser.objects.create(
            username='a@x.com', email='hsadmin@zillah.test')
        self.position = HSAdministratorPosition.objects.create(
            hsadmin=HSAdministrator.objects.create(user=admin_user),
            highschool=self.hs, position=HSPosition.objects.create(name='P'),
            status='Active')

    def _send(self):
        from ..views.ce import send_pending_reminder
        request = RequestFactory().get('/', {
            'highschool_id': str(self.hs.id),
            'academic_year_id': str(self.ay.id),
            'admin_ids[]': [str(self.position.id)]})
        with mock.patch(f'{PKG}.views.ce.send_html_mail') as send:
            send_pending_reminder(request)
        return send

    @override_settings(DEBUG=True)
    def test_debug_without_testers_sends_nothing(self):
        self._config(testers='', pending_notification_message='Hi')
        self.assertFalse(self._send().called)

    @override_settings(DEBUG=True)
    def test_debug_routes_to_testers(self):
        self._config(testers='qa@tenant.test', pending_notification_message='Hi')
        self.assertEqual(self._sent_to(self._send()), ['qa@tenant.test'])


class ConfirmationEmailTests(_Base):
    def _send(self):
        from ..views.api import FutureSectionsActionViewSet
        request = RequestFactory().post('/')
        request.user = CustomUser.objects.create(
            username='h@x.com', email='hsadmin@zillah.test')
        with mock.patch(f'{PKG}.views.api.send_html_mail') as send:
            FutureSectionsActionViewSet()._send_confirmation_email(
                request, {'academic_year': self.ay, 'highschools': [self.hs]})
        return send

    @override_settings(DEBUG=True)
    def test_debug_without_testers_sends_nothing(self):
        self._config(testers='', confirmation_subject='S',
                     confirmation_message='M')
        self.assertFalse(self._send().called)

    @override_settings(DEBUG=True)
    def test_debug_routes_to_testers(self):
        self._config(testers='qa@tenant.test', confirmation_subject='S',
                     confirmation_message='M')
        self.assertEqual(self._sent_to(self._send()), ['qa@tenant.test'])


class NoPersonalAddressesTests(SimpleTestCase):
    """No shipped (non-test) file names a personal mailbox."""
    PATTERN = re.compile(r'kadaji@|akadajis@|@gmail\.com|@syr\.edu')

    def test_no_personal_addresses_in_package_source(self):
        hits = []
        for root, dirs, files in os.walk(PKG_DIR):
            dirs[:] = [d for d in dirs if d not in ('tests', '__pycache__')]
            for name in files:
                if not name.endswith(('.py', '.html', '.js')):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding='utf-8', errors='ignore') as fh:
                    for n, line in enumerate(fh, 1):
                        if self.PATTERN.search(line):
                            hits.append(f'{os.path.relpath(path, PKG_DIR)}:{n}')
        self.assertEqual(hits, [])
