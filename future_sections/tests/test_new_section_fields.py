from django import forms
from django.test import SimpleTestCase

from ..schemas import TeachingSectionFieldSchema


class NewFieldDeclarationTests(SimpleTestCase):
    def test_all_four_new_fields_are_available(self):
        names = TeachingSectionFieldSchema.get_available_field_names()
        for name in ('start_date', 'end_date', 'assessment_upload',
                     'new_teacher_email'):
            self.assertIn(name, names)

    def test_start_date_meta(self):
        meta = TeachingSectionFieldSchema.get_field_meta('start_date')
        self.assertEqual(meta.get('widget_type'), 'date')
        self.assertEqual(meta.get('field_type'), 'date')
        self.assertEqual(meta.get('default_label'), 'Start Date')

    def test_end_date_meta(self):
        meta = TeachingSectionFieldSchema.get_field_meta('end_date')
        self.assertEqual(meta.get('widget_type'), 'date')
        self.assertEqual(meta.get('default_label'), 'End Date')

    def test_end_date_does_not_depend_on_start_date(self):
        meta = TeachingSectionFieldSchema.get_field_meta('end_date')
        self.assertIsNone(meta.get('depends_on'))

    def test_assessment_upload_meta(self):
        meta = TeachingSectionFieldSchema.get_field_meta('assessment_upload')
        self.assertEqual(meta.get('widget_type'), 'file')
        self.assertEqual(meta.get('default_label'), 'Assessment Upload')

    def test_new_teacher_email_meta(self):
        meta = TeachingSectionFieldSchema.get_field_meta('new_teacher_email')
        self.assertEqual(meta.get('widget_type'), 'email')
        self.assertEqual(meta.get('default_label'), 'New Teacher Email')
        self.assertEqual(meta.get('depends_on'), 'teacher_changed')


class IntrospectionHelperTests(SimpleTestCase):
    def test_get_dependent_fields_maps_child_to_parent(self):
        deps = TeachingSectionFieldSchema.get_dependent_fields()
        self.assertEqual(deps.get('new_teacher_name'), 'teacher_changed')
        self.assertEqual(deps.get('new_teacher_email'), 'teacher_changed')
        self.assertEqual(deps.get('new_highschool_title'),
                         'highschool_title_changed')
        self.assertNotIn('estimated_enrollment', deps)

    def test_get_dependents_of_returns_declaration_order(self):
        self.assertEqual(
            TeachingSectionFieldSchema.get_dependents_of('teacher_changed'),
            ['new_teacher_name', 'new_teacher_email'])

    def test_get_dependents_of_unknown_parent_is_empty(self):
        self.assertEqual(
            TeachingSectionFieldSchema.get_dependents_of('notes'), [])

    def test_get_file_field_names(self):
        self.assertEqual(TeachingSectionFieldSchema.get_file_field_names(),
                         ['assessment_upload'])

    def test_get_date_field_names(self):
        self.assertEqual(TeachingSectionFieldSchema.get_date_field_names(),
                         ['start_date', 'end_date'])


class WidgetTypeTests(SimpleTestCase):
    def test_visible_file_field_is_a_filefield(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'assessment_upload', visible=True)
        self.assertIsInstance(field, forms.FileField)
        self.assertIsInstance(field.widget, forms.ClearableFileInput)
        self.assertEqual(field.label, 'Assessment Upload')

    def test_hidden_file_field_is_a_charfield(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'assessment_upload', visible=False)
        self.assertIsInstance(field, forms.CharField)
        self.assertNotIsInstance(field, forms.FileField)
        self.assertIsInstance(field.widget, forms.HiddenInput)

    def test_visible_date_field_is_a_datefield_with_date_input(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'start_date', visible=True)
        self.assertIsInstance(field, forms.DateField)
        # Django's Input.__init__ pops "type" out of attrs into
        # self.input_type (it never stays in widget.attrs) — that's the
        # correct, idiomatic mechanism Django uses to render
        # <input type="date">, so assert against input_type rather than
        # attrs.
        self.assertEqual(field.widget.input_type, 'date')

    def test_date_field_accepts_iso_and_us_formats(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'start_date', visible=True)
        self.assertIn('%Y-%m-%d', field.input_formats)
        self.assertIn('%m/%d/%Y', field.input_formats)

    def test_hidden_date_field_is_a_charfield(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'start_date', visible=False)
        self.assertIsInstance(field, forms.CharField)
        self.assertIsInstance(field.widget, forms.HiddenInput)

    def test_visible_email_field_is_an_emailfield(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'new_teacher_email', visible=True)
        self.assertIsInstance(field, forms.EmailField)

    def test_hidden_email_field_is_a_charfield(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'new_teacher_email', visible=False)
        self.assertIsInstance(field.widget, forms.HiddenInput)

    def test_required_flag_is_honoured_for_new_widget_types(self):
        for name in ('assessment_upload', 'start_date', 'new_teacher_email'):
            field = TeachingSectionFieldSchema.make_django_form_field(
                name, visible=True, required=True)
            self.assertTrue(field.required, name)

    def test_label_and_help_text_overrides_apply(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'assessment_upload', visible=True,
            label_override='Rubric', help_text_override='PDF only')
        self.assertEqual(field.label, 'Rubric')
        self.assertEqual(field.help_text, 'PDF only')
