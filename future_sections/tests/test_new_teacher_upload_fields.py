"""Two upload fields asked only when a new teacher is being added.

`new_teacher_syllabus` and `new_teacher_class_assessment` are deliberately
separate from the teaching form's `syllabus` and `assessment_upload`: a
tenant may collect documents in both places, and the two sets must not
share a storage key or a configuration entry.
"""
from django import forms as djforms
from django.test import SimpleTestCase

from ..schemas import TeachingSectionFieldSchema


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
