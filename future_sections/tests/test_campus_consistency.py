"""FS-01 campus consistency (#6).

Terms must belong to the request's academic year; the notify commands are
CampusCommands that work on their campus's records with that campus's
settings and host. Single-campus behaviour is unchanged.
"""
import importlib.util
import unittest
import uuid
from datetime import date
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from cis.models.course import Campus, Cohort, Course
from cis.models.customuser import CustomUser
from cis.models.highschool import HighSchool
from cis.models.settings import Setting
from cis.models.teacher import (
    Teacher, TeacherCourseCertificate, TeacherHighSchool)
from cis.models.term import AcademicYear, Term

from . import PKG
from .. import campus as fs_campus
from ..models import FutureCourse, SectionRequestReview

HAS_CAMPUS_CIS = bool(importlib.util.find_spec('cis.campus_context')) and \
    bool(importlib.util.find_spec('cis.management.campus_command'))
TODAY = date.today().strftime('%m/%d/%Y')


def _sfx():
    return uuid.uuid4().hex[:6]


class _People(TestCase):
    def _cert(self, course, hs):
        Group.objects.get_or_create(name='instructor')
        teacher = Teacher.objects.create(user=CustomUser.objects.create(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com'))
        return TeacherCourseCertificate.objects.create(
            teacher_highschool=TeacherHighSchool.objects.create(
                teacher=teacher, highschool=hs),
            course=course, status='Teaching')

    def _course(self):
        cohort = Cohort.objects.create(designator=f'C{_sfx()}', name='Co')
        return Course.objects.create(
            cohort=cohort, catalog_number='101', title='Alpha', name='A1',
            credit_hours=3, status='Active')


class TermYearTests(_People):
    def setUp(self):
        self.ay = AcademicYear.objects.create(name=f'AY-{_sfx()}')
        self.other_ay = AcademicYear.objects.create(name=f'AY-{_sfx()}')
        self.term = Term.objects.create(
            academic_year=self.ay, code='FA', label='Fall')
        self.foreign = Term.objects.create(
            academic_year=self.other_ay, code='FA', label='Other Fall')
        self.cert = self._cert(self._course(),
                               HighSchool.objects.create(name='HS'))

    def _fc(self, **kw):
        return FutureCourse(teacher_course=self.cert, academic_year=self.ay, **kw)

    def test_consistent_request_has_no_error(self):
        fc = self._fc(term=self.term, section_info={
            'teaching': 'yes', 'sections': [{'term': str(self.term.id)}]})
        self.assertEqual(fc.term_year_error(), '')

    def test_term_fk_from_another_year_is_rejected(self):
        self.assertIn('Other Fall', self._fc(term=self.foreign).term_year_error())

    def test_row_term_from_another_year_is_rejected(self):
        fc = self._fc(section_info={'teaching': 'yes', 'sections': [
            {'term': str(self.term.id)}, {'term': str(self.foreign.id)}]})
        self.assertIn('Other Fall', fc.term_year_error())

    def test_rows_about_to_be_saved_are_checked(self):
        fc = self._fc()
        self.assertTrue(fc.term_year_error([{'term': str(self.foreign.id)}]))
        self.assertEqual(fc.term_year_error([{'term': 'garbage'}]), '')

    def test_dead_model_guards_are_gone(self):
        # Review M5: nothing called FutureCourse.clean() and no get_or_add
        # caller passes rows; the views own the check (test_term_year_views).
        from django.db import models as dj_models
        self.assertIs(FutureCourse.clean, dj_models.Model.clean)


class SingleCampusLinkTests(TestCase):
    @override_settings(MULTI_CAMPUS=False, SITE_URL='https://old.example')
    def test_single_campus_keeps_site_url(self):
        self.assertEqual(fs_campus.site_link('/x/'), 'https://old.example/x/')
        self.assertIsNone(fs_campus.serving_campus())
        self.assertFalse(fs_campus.other_campus(None))

    def test_without_campus_cis_falls_back(self):
        with mock.patch.object(fs_campus, '_campus_context', return_value=None), \
                override_settings(SITE_URL='https://old.example'):
            self.assertEqual(fs_campus.site_link('/x/'),
                             'https://old.example/x/')
            self.assertFalse(fs_campus.is_multi_campus())

    def test_without_campus_command_uses_base_command(self):
        from django.core.management.base import BaseCommand
        with mock.patch('importlib.util.find_spec', return_value=None):
            self.assertIs(fs_campus.command_base(), BaseCommand)


@unittest.skipUnless(HAS_CAMPUS_CIS, 'cis without multi-campus support')
class MultiCampusNotifyTests(_People):
    def setUp(self):
        from cis.campus_context import campus_context
        self.campus_context = campus_context
        prefix = settings.CAMPUS_CODE_PREFIX
        self.c1, self.c2 = [
            Campus.objects.create(
                name=f'{n}-{_sfx()}', code=f'{prefix}_{_sfx()}',
                site=Site.objects.create(domain=f'{n}-{_sfx()}.test', name=n))
            for n in ('one', 'two')]
        self.ay1 = AcademicYear.objects.create(name='2099-2100', campus=self.c1)
        self.ay2 = AcademicYear.objects.create(name='2099-2100', campus=self.c2)
        for campus, ay, subject in ((self.c1, self.ay1, 'C1 subject'),
                                    (self.c2, self.ay2, 'C2 subject')):
            Setting.objects.create(key='cis_future_sections', campus=campus, value={
                'require_review': '1', 'academic_year': str(ay.id),
                'review_notification_dates': TODAY,
                'review_notification_subject': subject,
                'review_notification_message': '{{requests}} {{link}}',
                'pending_notification_dates': TODAY,
                'pending_notification_message': 'Hi {{link}}',
            })
        self.reviewer = CustomUser.objects.create(
            username=f'{_sfx()}@x.com', email='rev@x.com')
        course = self._course()
        self.fc1 = self._pending(course, self.ay1, 'School One')
        self.fc2 = self._pending(course, self.ay2, 'School Two')

    def _pending(self, course, ay, school):
        fc = FutureCourse.objects.create(
            teacher_course=self._cert(course, HighSchool.objects.create(name=school)),
            academic_year=ay, status='pending_review', review_round=1)
        SectionRequestReview.objects.create(
            future_course=fc, reviewer=self.reviewer, round=1, role='Faculty')
        return fc

    def test_commands_are_campus_commands(self):
        from cis.management.campus_command import CampusCommand
        from ..management.commands import (
            notify_pending_reviews, notify_pending_section_requests)
        self.assertTrue(issubclass(notify_pending_reviews.Command, CampusCommand))
        self.assertTrue(issubclass(
            notify_pending_section_requests.Command, CampusCommand))

    @override_settings(MULTI_CAMPUS=True)
    def test_multi_campus_without_campus_is_an_error(self):
        with self.assertRaises(CommandError):
            call_command('notify_pending_reviews', stdout=StringIO())

    @override_settings(MULTI_CAMPUS=True, DEBUG=False)
    def test_c2_run_uses_c2_records_settings_and_host(self):
        with mock.patch('mailer.send_html_mail') as send:
            call_command('notify_pending_reviews', campus=self.c2.code,
                         stdout=StringIO())
        self.assertEqual(send.call_count, 1)
        subject, text = send.call_args.args[0], send.call_args.args[1]
        self.assertEqual(subject, 'C2 subject')
        self.assertIn(self.c2.site.domain, text)
        self.assertNotIn(self.c1.site.domain, text)
        self.assertIn('School Two', text)
        self.assertNotIn('School One', text)

    @override_settings(MULTI_CAMPUS=True)
    def test_site_link_uses_the_records_campus(self):
        with self.campus_context(self.c1):
            link = fs_campus.site_link('/p/', self.ay2)
        self.assertEqual(link, f'https://{self.c2.site.domain}/p/')

    @override_settings(MULTI_CAMPUS=True)
    def test_pending_requests_refuse_another_campus_year(self):
        # c2's run, but its setting names c1's year.
        with self.campus_context(self.c2):
            row = Setting.objects.get(key='cis_future_sections')
            row.value['academic_year'] = str(self.ay1.id)
            row.save()
            with mock.patch(f'{PKG}.utils.get_lookback_universe') as uni:
                uni.return_value.exists.return_value = True
                uni.return_value.exclude.return_value.values.return_value \
                    .annotate.return_value = [{
                        'teacher_highschool__highschool__id': uuid.uuid4(),
                        'pending_count': 1}]
                summary, log = FutureCourse.notify_pending_section_requests()
        self.assertIn('belongs to another campus', summary)


@unittest.skipUnless(HAS_CAMPUS_CIS, 'cis without multi-campus support')
@override_settings(MULTI_CAMPUS=True)
class MultiCampusCEScopeTests(_People):
    """CE reconciliation, the SIS-sections modal and the CE list feed refuse
    another campus's year or request (review I3)."""

    def setUp(self):
        from cis.campus_context import campus_context
        from django.urls import reverse
        from .test_email_new_teacher_send import _safe_force_login
        self.campus_context = campus_context
        prefix = settings.CAMPUS_CODE_PREFIX
        self.c1, self.c2 = [
            Campus.objects.create(
                name=f'{n}-{_sfx()}', code=f'{prefix}_{_sfx()}',
                site=Site.objects.create(domain=f'{n}-{_sfx()}.test', name=n))
            for n in ('one', 'two')]
        self.ay1 = AcademicYear.objects.create(name=f'A1-{_sfx()}', campus=self.c1)
        self.ay2 = AcademicYear.objects.create(name=f'A2-{_sfx()}', campus=self.c2)
        self.t1 = Term.objects.create(academic_year=self.ay1, code='FA6L', label='Fall')
        self.t2 = Term.objects.create(academic_year=self.ay2, code='FA', label='Fall')
        for campus, ay, code in ((self.c1, self.ay1, '6L'), (self.c2, self.ay2, '')):
            Setting.objects.create(key='cis_future_sections', campus=campus, value={
                'academic_year': str(ay.id), 'sis_full_year_term_code': code})
        with campus_context(self.c1):
            course = self._course()
            self.fc1 = FutureCourse.objects.create(
                teacher_course=self._cert(course, HighSchool.objects.create(name='S1')),
                academic_year=self.ay1, section_info={'teaching': 'yes', 'sections': []})
            self.fc2 = FutureCourse.objects.create(
                teacher_course=self._cert(course, HighSchool.objects.create(name='S2')),
                academic_year=self.ay2, section_info={'teaching': 'yes', 'sections': []})
        Group.objects.get_or_create(name='ce')
        self.ce = CustomUser.objects.create_user(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', password='pw',
            is_superuser=True)  # passes CampusMiddleware's process_campuses gate
        self.ce.groups.add(Group.objects.get(name='ce'))
        _safe_force_login(self.client, self.ce)
        self.actions = reverse('future_sections_ce:future_sections_actions')
        self.recon = reverse('future_sections_ce:sis_reconciliation')
        self.feed = reverse('future_sections_ce:future_class_section-list')

    def _serve(self, campus):
        # CampusMiddleware serves the campus whose Site matches the host.
        from contextlib import contextmanager

        @contextmanager
        def served():
            self.client.defaults['HTTP_HOST'] = campus.site.domain
            try:
                yield
            finally:
                self.client.defaults.pop('HTTP_HOST', None)
        return served()

    def test_reconciliation_404s_for_another_campus_year(self):
        with self._serve(self.c1):
            ok = self.client.get(self.recon, {'academic_year': str(self.ay1.id)})
            other = self.client.get(self.recon, {'academic_year': str(self.ay2.id)})
            csv_other = self.client.get(self.recon, {
                'academic_year': str(self.ay2.id), 'format': 'csv'})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(other.status_code, 404)
        self.assertEqual(csv_other.status_code, 404)

    def test_modal_get_and_post_404_for_another_campus_request(self):
        with self._serve(self.c1):
            ok = self.client.get(self.actions, {
                'action': 'sis-sections', 'future_course_id': str(self.fc1.id)})
            get = self.client.get(self.actions, {
                'action': 'sis-sections', 'future_course_id': str(self.fc2.id)})
            post = self.client.post(self.actions, {
                'action': 'sis-sections', 'future_course_id': str(self.fc2.id),
                'sis_sections': []})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(get.status_code, 404)
        self.assertEqual(post.status_code, 404)

    def test_ce_list_feed_hides_another_campus_requests(self):
        with self._serve(self.c1):
            response = self.client.get(self.feed, {
                'format': 'json', 'academic_year': ''})
        data = response.json()
        ids = {r['id'] for r in data.get('results', data)}
        self.assertIn(str(self.fc1.id), ids)
        self.assertNotIn(str(self.fc2.id), ids)

    def test_full_year_code_is_read_in_the_records_campus(self):
        from ..sis_reconcile import _full_year_code
        with self.campus_context(self.c2):
            self.assertEqual(_full_year_code(self.ay1), '6L')
            self.assertEqual(_full_year_code(self.ay2), '')


@unittest.skipUnless(HAS_CAMPUS_CIS, 'cis without multi-campus support')
class CampuslessYearReviewTests(MultiCampusNotifyTests):
    """Requests whose year has no campus are skipped by every campus's run;
    the run says so instead of dropping them silently (review I4)."""

    def setUp(self):
        super().setUp()
        self.ay_none = AcademicYear.objects.create(name='Orphan-2099')
        with self.campus_context(self.c1):
            self.orphan = self._pending(self._course(), self.ay_none, 'School X')

    @override_settings(MULTI_CAMPUS=True, DEBUG=False)
    def test_campusless_rows_are_logged_once(self):
        with self.campus_context(self.c1), \
                mock.patch('mailer.send_html_mail'), \
                self.assertLogs(f'{PKG}.models', level='WARNING') as logs:
            summary, log = FutureCourse.notify_pending_reviews()
        warnings = [r for r in logs.records if 'no campus' in r.getMessage()]
        self.assertEqual(len(warnings), 1)
        self.assertIn('1 ', warnings[0].getMessage())
        skipped = [s for s in log['skipped']
                   if isinstance(s, dict) and s.get('reason') == 'academic year has no campus']
        self.assertEqual(skipped[0]['count'], 1)
        self.assertIn('Orphan-2099', skipped[0]['academic_years'])
