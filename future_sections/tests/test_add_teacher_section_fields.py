"""Add Teacher must save the Teaching Form Fields it renders.

`AddNewTeacherForm` inherits the teaching form, so a tenant that turns on
`class_period` or `start_date` sees those inputs on the Add Teacher page.
`save()` hand-built the stored section from a four-key whitelist, so every
answer outside it was validated and then dropped — the request landed with
only the term and estimated enrollment.
"""
import json
from unittest import mock

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from cis.models.course import Campus, Cohort, Course
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.term import AcademicYear, Term

from ..forms import AddNewTeacherForm


TEACHING_FIELDS = [
    'term', 'class_period', 'teacher_changed', 'new_teacher_name',
    'new_teacher_email', 'start_date', 'end_date', 'assessment_upload',
]


class _FakeStorage:
    def save(self, name, content):
        return name

    def url(self, name):
        return f'https://files.test/{name}'


class AddTeacherSavesTeachingFieldsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        from cis.models.highschool import HighSchool
        from cis.models.highschool_administrator import (
            HSAdministrator, HSAdministratorPosition, HSPosition,
        )

        Group.objects.get_or_create(name='instructor')
        Group.objects.get_or_create(name='highschool_admin')
        cls.user = CustomUser.objects.create(
            username='hsa-tf@x.com', email='hsa-tf@x.com', is_active=True)
        cls.user.groups.add(Group.objects.get(name='highschool_admin'))

        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.term = Term.objects.create(
            label='Fall 2099', code='F99', academic_year=cls.ay)
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Stocked', code='S')
        cls.course = Course.objects.create(
            name='A1', title='Alpha Active', cohort=cls.cohort,
            catalog_number='101', credit_hours=3, campus=cls.campus,
            status='Active')

        cls.highschool = HighSchool.objects.create(name='Test HS')
        position = HSPosition.objects.create(name='Coordinator')
        hsadmin = HSAdministrator.objects.create(user=cls.user)
        HSAdministratorPosition.objects.create(
            hsadmin=hsadmin, highschool=cls.highschool, position=position,
            status='Active')

    def setUp(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'academic_year': str(self.ay.id),
                'teaching_form_config': json.dumps({
                    'fields': TEACHING_FIELDS,
                    'required': ['term'],
                }),
                'add_teacher_form_config': json.dumps({
                    'fields': ['teacher_first_name', 'teacher_last_name',
                               'teacher_email'],
                }),
            },
        )

    def _saved_section(self, files=None, **overrides):
        req = RequestFactory().post('/', data=files or {})
        req.user = self.user
        data = {
            'action': 'add_new_teacher',
            'academic_year_id': str(self.ay.id),
            'highschool': str(self.highschool.id),
            'term': str(self.term.id),
            'course': str(self.course.id),
            'teacher_first_name': 'Mike',
            'teacher_last_name': 'Moeller',
            'teacher_email': 'moeller@example.com',
            'class_period': '3rd period',
            'teacher_changed': 'yes',
            'new_teacher_name': 'Dana Scully',
            'new_teacher_email': 'dana@example.com',
            'start_date': '09/01/2099',
            'end_date': '05/30/2100',
        }
        data.update(overrides)
        form = AddNewTeacherForm(req, self.ay, 'pathways', data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        with mock.patch(
                'cis.backends.storage_backend.PrivateMediaStorage',
                _FakeStorage):
            record = form.save(req, self.ay)
        return record.section_info['sections'][-1]

    def test_class_period_is_saved(self):
        self.assertEqual(self._saved_section()['class_period'], '3rd period')

    def test_teacher_changed_answer_and_its_dependents_are_saved(self):
        section = self._saved_section()
        self.assertEqual(section['teacher_changed'], 'yes')
        self.assertEqual(section['new_teacher_name'], 'Dana Scully')
        self.assertEqual(section['new_teacher_email'], 'dana@example.com')

    def test_dates_are_saved_json_serialisable(self):
        section = self._saved_section()
        self.assertEqual(section['start_date'], '2099-09-01')
        self.assertEqual(section['end_date'], '2100-05-30')

    def test_uploaded_file_is_saved_under_its_field_name(self):
        section = self._saved_section(
            files={'assessment_upload': SimpleUploadedFile('r.pdf', b'x')})
        # Stored under the record's own prefix, as the formset path does.
        self.assertRegex(
            section['assessment_upload'],
            r'^https://files\.test/future_section/[0-9a-f-]+/r\.pdf$')

    def test_file_field_with_no_upload_is_empty_not_missing(self):
        self.assertEqual(self._saved_section()['assessment_upload'], '')

    def test_term_and_estimated_enrollment_still_saved(self):
        section = self._saved_section()
        self.assertEqual(section['term'], str(self.term.id))
        self.assertEqual(
            section['term_name'], '2099-2100, Fall 2099')
        self.assertEqual(section['estimated_enrollment'], '')
