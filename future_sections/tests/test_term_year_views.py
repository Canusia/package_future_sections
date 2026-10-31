"""Teaching-form saves vs. the request's academic year (review I2, #6).

The term dropdown must offer the *request's* year, not the configured cycle
year, so CE can edit a request from any year; a term from another year is
refused with a 400 on both the CE and the school-side (API) save.
"""
import json
import uuid

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from cis.models.course import Cohort, Course
from cis.models.customuser import CustomUser
from cis.models.highschool import HighSchool
from cis.models.highschool_administrator import (
    HSAdministrator, HSAdministratorPosition, HSPosition)
from cis.models.settings import Setting
from cis.models.teacher import (
    Teacher, TeacherCourseCertificate, TeacherHighSchool)
from cis.models.term import AcademicYear, Term

from ..forms import TeacherCourseSectionForm
from ..models import FutureCourse
from .test_email_new_teacher_send import _safe_force_login


def _sfx():
    return uuid.uuid4().hex[:6]


class _Base(TestCase):
    def setUp(self):
        for name in ('ce', 'highschool_admin', 'instructor'):
            Group.objects.get_or_create(name=name)
        self.configured = AcademicYear.objects.create(name=f'CFG-{_sfx()}')
        self.cfg_fall = Term.objects.create(
            academic_year=self.configured, code='FA', label='Cfg Fall')
        self.other = AcademicYear.objects.create(name=f'OLD-{_sfx()}')
        self.old_fall = Term.objects.create(
            academic_year=self.other, code='FA', label='Old Fall')
        Setting.objects.update_or_create(
            key='cis_future_sections', defaults={'value': {
                'academic_year': str(self.configured.id),
                'teaching_form_config': json.dumps({'fields': ['term']}),
            }})
        cohort = Cohort.objects.create(designator=f'L{_sfx()}', name='Lit')
        course = Course.objects.create(
            cohort=cohort, catalog_number='139', title='LIT 139',
            name='LIT 139', credit_hours=3, status='Active')
        self.hs = HighSchool.objects.create(name=f'Alpha {_sfx()}')
        teacher = Teacher.objects.create(user=CustomUser.objects.create(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com'))
        self.cert = TeacherCourseCertificate.objects.create(
            teacher_highschool=TeacherHighSchool.objects.create(
                teacher=teacher, highschool=self.hs),
            course=course, status='Teaching')

    def _data(self, term, year):
        return {
            'teacher_course_certificate_id': str(self.cert.certificate_id),
            'academic_year_id': str(year.id),
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            'form-0-term': str(term.id),
        }

    def _rows(self, year):
        fc = FutureCourse.objects.get(teacher_course=self.cert,
                                      academic_year=year)
        return [r['term'] for r in fc.section_info['sections']]


class FormTermChoicesTests(_Base):
    def test_terms_come_from_the_given_year(self):
        form = TeacherCourseSectionForm(academic_year=self.other)
        self.assertEqual(list(form.fields['term'].queryset), [self.old_fall])

    def test_falls_back_to_the_configured_year(self):
        form = TeacherCourseSectionForm()
        self.assertEqual(list(form.fields['term'].queryset), [self.cfg_fall])


class CETeachingSaveTests(_Base):
    def setUp(self):
        super().setUp()
        self.ce = CustomUser.objects.create_user(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', password='pw')
        self.ce.groups.add(Group.objects.get(name='ce'))
        _safe_force_login(self.client, self.ce)
        self.url = reverse('future_sections_ce:future_sections_actions')

    def _post(self, term, year):
        data = self._data(term, year)
        data['action'] = 'teaching-section'
        return self.client.post(self.url, data)

    def test_ce_edits_a_request_from_a_non_configured_year(self):
        response = self._post(self.old_fall, self.other)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._rows(self.other), [str(self.old_fall.id)])

    def test_get_offers_the_requests_year_terms(self):
        response = self.client.get(self.url, {
            'action': 'teaching-section',
            'course_certificate': str(self.cert.certificate_id),
            'academic_year_id': str(self.other.id)})
        self.assertContains(response, 'Old Fall')
        self.assertNotContains(response, 'Cfg Fall')

    def test_term_from_another_year_is_a_400(self):
        response = self._post(self.cfg_fall, self.other)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._rows(self.other), [])

    def test_stored_foreign_term_fk_is_a_400_with_details(self):
        fc = FutureCourse.get_or_add(self.cert, self.other)
        FutureCourse.objects.filter(pk=fc.pk).update(term=self.cfg_fall)
        response = self._post(self.old_fall, self.other)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Cfg Fall', response.json()['details'])


class SchoolTeachingSaveTests(_Base):
    def setUp(self):
        super().setUp()
        self.user = CustomUser.objects.create_user(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', password='pw')
        self.user.groups.add(Group.objects.get(name='highschool_admin'))
        HSAdministratorPosition.objects.create(
            hsadmin=HSAdministrator.objects.create(user=self.user),
            highschool=self.hs, position=HSPosition.objects.create(name='C'),
            status='Active')
        _safe_force_login(self.client, self.user)
        self.url = reverse(
            'future_sections_highschool_admin:actions-mark-teaching')

    def test_school_saves_a_term_of_the_requests_year(self):
        response = self.client.post(
            self.url, self._data(self.old_fall, self.other))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._rows(self.other), [str(self.old_fall.id)])

    def test_term_from_another_year_is_a_400(self):
        response = self.client.post(
            self.url, self._data(self.cfg_fall, self.other))
        self.assertEqual(response.status_code, 400)

    def test_stored_foreign_term_fk_is_a_400_with_details(self):
        fc = FutureCourse.get_or_add(self.cert, self.other)
        FutureCourse.objects.filter(pk=fc.pk).update(term=self.cfg_fall)
        response = self.client.post(
            self.url, self._data(self.old_fall, self.other))
        self.assertEqual(response.status_code, 400)
        self.assertIn('Cfg Fall', response.json()['details'])
