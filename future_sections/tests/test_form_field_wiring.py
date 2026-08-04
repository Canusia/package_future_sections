import json

from django import forms
from django.test import TestCase

from cis.models.settings import Setting
from future_sections.future_sections.forms import TeacherCourseSectionForm


class _ConfigMixin:
    def _make_setting(self, fields, required=('term',)):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': list(fields),
                    'required': list(required),
                }),
            },
        )


class DependentFieldVisibilityTests(_ConfigMixin, TestCase):
    def test_enabling_teacher_changed_makes_both_dependents_visible(self):
        self._make_setting(fields=('term', 'teacher_changed'))
        form = TeacherCourseSectionForm()
        for name in ('new_teacher_name', 'new_teacher_email'):
            self.assertNotIsInstance(
                form.fields[name].widget, forms.HiddenInput, name)

    def test_dependents_are_hidden_when_parent_is_not_enabled(self):
        self._make_setting(fields=('term',))
        form = TeacherCourseSectionForm()
        for name in ('new_teacher_name', 'new_teacher_email'):
            self.assertIsInstance(
                form.fields[name].widget, forms.HiddenInput, name)

    def test_new_teacher_email_is_an_emailfield_when_visible(self):
        self._make_setting(fields=('term', 'teacher_changed'))
        form = TeacherCourseSectionForm()
        self.assertIsInstance(form.fields['new_teacher_email'],
                              forms.EmailField)

    def test_highschool_title_dependent_still_works(self):
        self._make_setting(fields=('term', 'highschool_title_changed'))
        form = TeacherCourseSectionForm()
        self.assertNotIsInstance(
            form.fields['new_highschool_title'].widget, forms.HiddenInput)


class FileCompanionFieldTests(_ConfigMixin, TestCase):
    def test_visible_file_field_gets_a_hidden_existing_companion(self):
        self._make_setting(fields=('term', 'assessment_upload'))
        form = TeacherCourseSectionForm()
        self.assertIn('assessment_upload_existing', form.fields)
        self.assertIsInstance(
            form.fields['assessment_upload_existing'].widget,
            forms.HiddenInput)
        self.assertFalse(form.fields['assessment_upload_existing'].required)

    def test_no_companion_when_file_field_is_not_visible(self):
        self._make_setting(fields=('term',))
        form = TeacherCourseSectionForm()
        self.assertNotIn('assessment_upload_existing', form.fields)

    def test_companion_is_seeded_with_the_stored_url(self):
        self._make_setting(fields=('term', 'assessment_upload'))
        form = TeacherCourseSectionForm(
            initial={'assessment_upload': 'https://x.test/a.pdf'})
        self.assertEqual(
            form.fields['assessment_upload_existing'].initial,
            'https://x.test/a.pdf')

    def test_label_gains_a_download_link_when_a_file_is_stored(self):
        self._make_setting(fields=('term', 'assessment_upload'))
        form = TeacherCourseSectionForm(
            initial={'assessment_upload': 'https://x.test/a.pdf'})
        label = str(form.fields['assessment_upload'].label)
        self.assertIn('https://x.test/a.pdf', label)
        self.assertIn('Assessment Upload', label)

    def test_label_is_plain_when_no_file_is_stored(self):
        self._make_setting(fields=('term', 'assessment_upload'))
        form = TeacherCourseSectionForm()
        self.assertEqual(form.fields['assessment_upload'].label,
                         'Assessment Upload')

    def test_syllabus_handling_is_unchanged(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': ['term'],
                    'required': ['term'],
                    'show_syllabus': True,
                }),
            },
        )
        form = TeacherCourseSectionForm(
            initial={'file': 'https://x.test/syllabus.pdf'})
        self.assertIn('https://x.test/syllabus.pdf',
                      str(form.fields['syllabus'].label))
        self.assertNotIn('syllabus_existing', form.fields)
