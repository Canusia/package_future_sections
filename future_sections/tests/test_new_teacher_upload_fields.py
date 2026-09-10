"""Two upload fields asked only when a new teacher is being added.

`new_teacher_syllabus` and `new_teacher_class_assessment` are deliberately
separate from the teaching form's `syllabus` and `assessment_upload`: a
tenant may collect documents in both places, and the two sets must not
share a storage key or a configuration entry.
"""
import json

from crispy_forms.utils import render_crispy_form
from django import forms as djforms
from django.test import RequestFactory, SimpleTestCase, TestCase

from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from ..forms import TeacherCourseSectionForm
from ..schemas import TeachingSectionFieldSchema
from ..settings.future_sections import future_sections


NEW_UPLOAD_FIELDS = ('new_teacher_syllabus', 'new_teacher_class_assessment')


class NewTeacherUploadSchemaTests(SimpleTestCase):

    def test_both_fields_are_available_in_the_schema(self):
        names = TeachingSectionFieldSchema.get_available_field_names()
        for name in NEW_UPLOAD_FIELDS:
            self.assertIn(name, names)

    def test_both_are_file_widgets(self):
        for name in NEW_UPLOAD_FIELDS:
            meta = TeachingSectionFieldSchema.get_field_meta(name)
            self.assertEqual(meta.get('widget_type'), 'file', name)
            self.assertEqual(meta.get('field_type'), 'string', name)

    def test_default_labels_omit_the_new_teacher_prefix(self):
        # The `new_` prefix keeps the stored keys distinct from the teaching
        # form's uploads; it is not something the person filling the form
        # should have to read.
        self.assertEqual(
            TeachingSectionFieldSchema.get_field_meta(
                'new_teacher_syllabus')['default_label'],
            'Syllabus')
        self.assertEqual(
            TeachingSectionFieldSchema.get_field_meta(
                'new_teacher_class_assessment')['default_label'],
            'Class Assessment')

    def test_neither_field_is_conditional(self):
        # `depends_on` would route them through the dependent-field render
        # branch, which emits no `_existing` companion — see the note on
        # get_existing_file_field.
        for name in NEW_UPLOAD_FIELDS:
            self.assertIsNone(
                TeachingSectionFieldSchema.get_field_meta(name).get(
                    'depends_on'), name)

    def test_they_join_the_file_field_list_in_declaration_order(self):
        self.assertEqual(
            TeachingSectionFieldSchema.get_file_field_names(),
            ['assessment_upload', 'new_teacher_syllabus',
             'new_teacher_class_assessment'])

    def test_visible_build_gives_a_real_file_field(self):
        for name in NEW_UPLOAD_FIELDS:
            field = TeachingSectionFieldSchema.make_django_form_field(
                name, visible=True)
            self.assertIsInstance(field, djforms.FileField, name)
            self.assertIsInstance(
                field.widget, djforms.ClearableFileInput, name)

    def test_hidden_build_gives_a_charfield_carrying_the_stored_url(self):
        for name in NEW_UPLOAD_FIELDS:
            field = TeachingSectionFieldSchema.make_django_form_field(
                name, visible=False)
            self.assertIsInstance(field, djforms.CharField, name)
            self.assertNotIsInstance(field, djforms.FileField, name)
            self.assertIsInstance(field.widget, djforms.HiddenInput, name)


class AddTeacherOnlyMembershipTests(SimpleTestCase):

    def test_both_fields_are_declared_add_teacher_only(self):
        self.assertEqual(
            set(TeacherCourseSectionForm.ADD_TEACHER_ONLY_FIELDS),
            {'course_type', 'course_request_type',
             'new_teacher_syllabus', 'new_teacher_class_assessment'})


class TeachingFormExclusionTests(TestCase):
    """The ordinary teaching form never asks for them, whatever it is told."""

    def _make_setting(self):
        # Listed visible AND required in the teaching config — the
        # configuration that would render them there if the exclusion broke.
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': ['term', 'new_teacher_syllabus',
                               'new_teacher_class_assessment'],
                    'required': ['term', 'new_teacher_syllabus',
                                 'new_teacher_class_assessment'],
                }),
            },
        )

    def test_fields_are_hidden_even_when_the_teaching_config_lists_them(self):
        self._make_setting()
        form = TeacherCourseSectionForm()
        for name in NEW_UPLOAD_FIELDS:
            self.assertIsInstance(
                form.fields[name].widget, djforms.HiddenInput, name)

    def test_fields_are_not_required_on_the_teaching_form(self):
        self._make_setting()
        form = TeacherCourseSectionForm()
        for name in NEW_UPLOAD_FIELDS:
            self.assertFalse(form.fields[name].required, name)

    def test_fields_are_not_file_fields_on_the_teaching_form(self):
        # A FileField here would demand a multipart upload to re-save a row
        # whose document was collected on the Add Teacher form.
        self._make_setting()
        form = TeacherCourseSectionForm()
        for name in NEW_UPLOAD_FIELDS:
            self.assertNotIsInstance(
                form.fields[name], djforms.FileField, name)


class SettingsCardRowTests(TestCase):
    """Each add-teacher-only field gets a configuration row on the card."""

    def test_add_teacher_card_has_a_row_for_each_new_field(self):
        user = CustomUser.objects.create(
            username='ce-upload@x.com', email='ce-upload@x.com',
            is_active=True)
        request = RequestFactory().get(
            '/?report_id=0f4e3b1a-1111-2222-3333-444455556666')
        request.user = user

        html = render_crispy_form(future_sections(request))
        for name in NEW_UPLOAD_FIELDS:
            self.assertIn(
                f'class="atfc-visible" data-field="{name}"', html, name)
            self.assertIn(
                f'class="atfc-required" data-field="{name}"', html, name)

    def test_new_fields_are_absent_from_the_teaching_card(self):
        user = CustomUser.objects.create(
            username='ce-upload2@x.com', email='ce-upload2@x.com',
            is_active=True)
        request = RequestFactory().get(
            '/?report_id=0f4e3b1a-1111-2222-3333-444455556666')
        request.user = user

        html = render_crispy_form(future_sections(request))
        for name in NEW_UPLOAD_FIELDS:
            self.assertNotIn(
                f'class="tfc-visible" data-field="{name}"', html, name)
