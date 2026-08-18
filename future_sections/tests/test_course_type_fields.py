"""The two course-type fields belong to the Add Teacher form.

"Type of course" (`course_type`) and "This is a:" (`course_request_type`) are
only asked when a new teacher is being added, so `add_teacher_form_config`
drives them and the ordinary teaching form never renders them. Options come
from the `course_types` / `course_request_types` settings as pipe-delimited
value:Label pairs. A field with no configured options is not rendered at all —
without that rule, a tenant taking this release would get an empty and
by-default-required dropdown it cannot satisfy.
"""
import json

from django import forms as djforms
from django.contrib.auth.models import Group
from django.test import RequestFactory, SimpleTestCase, TestCase

from cis.models.course import Campus, Cohort, Course
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.term import AcademicYear

from ..forms import (
    AddNewTeacherForm, TeacherCourseSectionForm,
)
from ..schemas import TeachingSectionFieldSchema


COURSE_TYPES = 'dual:Dual Credit|cpl:Credit for Prior Learning (CPL)'
COURSE_REQUEST_TYPES = 'new:New Course|new_instructor:With a new instructor'


class CourseTypeSchemaTests(SimpleTestCase):

    def test_both_fields_are_available_in_the_schema(self):
        names = TeachingSectionFieldSchema.get_available_field_names()
        self.assertIn('course_type', names)
        self.assertIn('course_request_type', names)

    def test_default_labels(self):
        self.assertEqual(
            TeachingSectionFieldSchema.get_field_meta(
                'course_type')['default_label'],
            'Type of course')
        self.assertEqual(
            TeachingSectionFieldSchema.get_field_meta(
                'course_request_type')['default_label'],
            'This is a:')

    def test_both_are_selects(self):
        for name in ('course_type', 'course_request_type'):
            self.assertEqual(
                TeachingSectionFieldSchema.get_field_meta(name)['widget_type'],
                'select', name)

    def test_no_choices_key_in_schema_metadata(self):
        # Options are per tenant and come from settings; a schema-level
        # default would ship one tenant's vocabulary to all of them.
        for name in ('course_type', 'course_request_type'):
            self.assertNotIn(
                'choices', TeachingSectionFieldSchema.get_field_meta(name))

    def test_they_are_declared_add_teacher_only(self):
        self.assertEqual(
            set(TeacherCourseSectionForm.ADD_TEACHER_ONLY_FIELDS),
            {'course_type', 'course_request_type'})


class TeachingFormExclusionTests(TestCase):
    """The plain teaching form never renders them, whatever it is told."""

    def _make_setting(self):
        # Both fields listed as visible AND required in the teaching config —
        # the configuration that used to render them there.
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': ['term', 'course_type', 'course_request_type'],
                    'required': ['term', 'course_type',
                                 'course_request_type'],
                }),
                'course_types': COURSE_TYPES,
                'course_request_types': COURSE_REQUEST_TYPES,
            },
        )

    def test_fields_are_hidden_even_when_the_teaching_config_lists_them(self):
        self._make_setting()
        form = TeacherCourseSectionForm()
        for name in ('course_type', 'course_request_type'):
            self.assertIsInstance(
                form.fields[name].widget, djforms.HiddenInput, name)

    def test_fields_are_not_required_on_the_teaching_form(self):
        self._make_setting()
        form = TeacherCourseSectionForm()
        for name in ('course_type', 'course_request_type'):
            self.assertFalse(form.fields[name].required, name)


def _hs_admin_user():
    Group.objects.get_or_create(name='highschool_admin')
    u = CustomUser.objects.create(
        username='hsa-ct@x.com', email='hsa-ct@x.com', is_active=True)
    u.groups.add(Group.objects.get(name='highschool_admin'))
    return u


class AddTeacherCourseTypeTests(TestCase):
    """`add_teacher_form_config` drives both selects on the Add Teacher form."""

    @classmethod
    def setUpTestData(cls):
        from cis.models.highschool import HighSchool
        from cis.models.highschool_administrator import (
            HSAdministrator, HSAdministratorPosition, HSPosition,
        )

        cls.user = _hs_admin_user()
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Stocked', code='S')
        Course.objects.create(
            name='A1', title='Alpha Active', cohort=cls.cohort,
            catalog_number='101', credit_hours=3, campus=cls.campus,
            status='Active')

        highschool = HighSchool.objects.create(name='Test HS')
        position = HSPosition.objects.create(name='Coordinator')
        hsadmin = HSAdministrator.objects.create(user=cls.user)
        HSAdministratorPosition.objects.create(
            hsadmin=hsadmin, highschool=highschool, position=position,
            status='Active')

    def _make_setting(self, fields=('course_type', 'course_request_type'),
                      required=(), labels=None,
                      course_types=COURSE_TYPES,
                      course_request_types=COURSE_REQUEST_TYPES):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'add_teacher_form_config': json.dumps({
                    'fields': list(fields),
                    'required': list(required),
                    'labels': labels or {},
                }),
                # Deliberately empty: the teaching config must have no say.
                'teaching_form_config': json.dumps({'fields': ['term']}),
                'course_types': course_types,
                'course_request_types': course_request_types,
            },
        )

    def _form(self, **kwargs):
        req = RequestFactory().get('/')
        req.user = self.user
        return AddNewTeacherForm(req, self.ay, 'pathways', **kwargs)

    def test_configured_field_renders_as_a_select_with_its_options(self):
        self._make_setting()
        form = self._form()
        self.assertIsInstance(
            form.fields['course_type'].widget, djforms.Select)
        choices = dict(form.fields['course_type'].choices)
        self.assertEqual(choices.get('dual'), 'Dual Credit')
        self.assertEqual(
            choices.get('cpl'), 'Credit for Prior Learning (CPL)')

    def test_field_left_out_of_the_config_is_hidden(self):
        self._make_setting(fields=('course_type',))
        form = self._form()
        self.assertIsInstance(
            form.fields['course_request_type'].widget, djforms.HiddenInput)
        self.assertFalse(form.fields['course_request_type'].required)

    def test_required_comes_from_the_add_teacher_config(self):
        self._make_setting(required=('course_type',))
        form = self._form()
        self.assertTrue(form.fields['course_type'].required)
        self.assertFalse(form.fields['course_request_type'].required)

    def test_custom_label_comes_from_the_add_teacher_config(self):
        self._make_setting(labels={'course_type': 'What kind of course?'})
        form = self._form()
        self.assertEqual(
            form.fields['course_type'].label, 'What kind of course?')

    def test_unconfigured_options_hide_the_field_even_if_visible(self):
        # Listed as visible and required, but no options to pick from.
        self._make_setting(required=('course_type',), course_types='')
        form = self._form()
        self.assertIsInstance(
            form.fields['course_type'].widget, djforms.HiddenInput)
        self.assertFalse(form.fields['course_type'].required)

    def test_the_other_field_is_unaffected_by_an_empty_list(self):
        self._make_setting(course_types='')
        form = self._form()
        choices = dict(form.fields['course_request_type'].choices)
        self.assertEqual(choices.get('new'), 'New Course')

    def test_stored_value_no_longer_configured_stays_selectable(self):
        self._make_setting()
        form = self._form(initial={'course_type': 'retired_option'})
        self.assertIn(
            'retired_option', dict(form.fields['course_type'].choices))
