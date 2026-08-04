import json

from django.test import TestCase

from cis.models.settings import Setting
from future_sections.future_sections.forms import TeacherCourseSectionForm
from future_sections.future_sections.templatetags.future_sections_tags import (
    dependent_fields,
    get_existing_file_field,
    is_dependent_field,
)


class _ConfigMixin:
    def _make_setting(self, fields):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': list(fields),
                    'required': ['term'],
                }),
            },
        )


class IsDependentFieldTests(TestCase):
    def test_dependent_names_are_reported(self):
        for name in ('new_teacher_name', 'new_teacher_email',
                     'new_highschool_title'):
            self.assertTrue(is_dependent_field(name), name)

    def test_independent_names_are_not(self):
        for name in ('term', 'estimated_enrollment', 'start_date',
                     'assessment_upload'):
            self.assertFalse(is_dependent_field(name), name)


class DependentFieldsTests(_ConfigMixin, TestCase):
    def test_returns_name_then_email_for_teacher_changed(self):
        self._make_setting(fields=('term', 'teacher_changed'))
        form = TeacherCourseSectionForm()
        names = [f.name for f in dependent_fields(form, 'teacher_changed')]
        self.assertEqual(names, ['new_teacher_name', 'new_teacher_email'])

    def test_returns_the_highschool_dependent(self):
        self._make_setting(fields=('term', 'highschool_title_changed'))
        form = TeacherCourseSectionForm()
        names = [f.name
                 for f in dependent_fields(form, 'highschool_title_changed')]
        self.assertEqual(names, ['new_highschool_title'])

    def test_returns_empty_for_a_field_with_no_dependents(self):
        self._make_setting(fields=('term', 'notes'))
        form = TeacherCourseSectionForm()
        self.assertEqual(dependent_fields(form, 'notes'), [])


class ExistingFileFieldTests(_ConfigMixin, TestCase):
    def test_returns_the_companion_when_the_file_field_is_visible(self):
        self._make_setting(fields=('term', 'assessment_upload'))
        form = TeacherCourseSectionForm()
        field = get_existing_file_field(form, 'assessment_upload')
        self.assertIsNotNone(field)
        self.assertEqual(field.name, 'assessment_upload_existing')

    def test_returns_none_when_there_is_no_companion(self):
        self._make_setting(fields=('term', 'notes'))
        form = TeacherCourseSectionForm()
        self.assertIsNone(get_existing_file_field(form, 'notes'))
