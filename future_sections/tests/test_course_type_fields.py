"""The two course-type fields are tenant-configured selects.

Options come from the `course_types` / `course_request_types` settings as
pipe-delimited value:Label pairs. A field with no configured options is not
rendered at all — without that rule, every tenant taking this release would
get an empty and by-default-required dropdown they cannot satisfy.
"""
import json

from django import forms as djforms
from django.test import SimpleTestCase, TestCase

from cis.models.settings import Setting
from future_sections.future_sections.forms import TeacherCourseSectionForm
from future_sections.future_sections.schemas import TeachingSectionFieldSchema


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


class CourseTypeFormWiringTests(TestCase):
    """Exercises TeacherCourseSectionForm's choice wiring."""

    def _make_setting(self, course_types='dual:Dual Credit|cpl:Credit for '
                       'Prior Learning (CPL)',
                       course_request_types='new:New Course|'
                       'new_instructor:With a new instructor',
                       fields=('term', 'course_type', 'course_request_type')):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': list(fields),
                    'required': ['term', 'course_type'],
                }),
                'course_types': course_types,
                'course_request_types': course_request_types,
            },
        )

    def test_configured_options_become_choices(self):
        self._make_setting()
        form = TeacherCourseSectionForm()
        choices = dict(form.fields['course_type'].choices)
        self.assertEqual(choices.get('dual'), 'Dual Credit')
        self.assertEqual(
            choices.get('cpl'), 'Credit for Prior Learning (CPL)')

    def test_unconfigured_field_is_hidden(self):
        self._make_setting(course_types='')
        form = TeacherCourseSectionForm()
        self.assertIsInstance(
            form.fields['course_type'].widget, djforms.HiddenInput)

    def test_unconfigured_field_is_not_required(self):
        # It is listed in `required`, but a field nobody can fill must not
        # block the form.
        self._make_setting(course_types='')
        form = TeacherCourseSectionForm()
        self.assertFalse(form.fields['course_type'].required)

    def test_the_other_field_is_unaffected_by_an_empty_list(self):
        self._make_setting(course_types='')
        form = TeacherCourseSectionForm()
        choices = dict(form.fields['course_request_type'].choices)
        self.assertEqual(choices.get('new'), 'New Course')

    def test_stored_value_no_longer_configured_stays_selectable(self):
        self._make_setting()
        form = TeacherCourseSectionForm(
            initial={'course_type': 'retired_option'})
        self.assertIn(
            'retired_option', dict(form.fields['course_type'].choices))
