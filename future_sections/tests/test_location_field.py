from django import forms
from django.test import SimpleTestCase

from future_sections.future_sections.schemas import TeachingSectionFieldSchema
from future_sections.future_sections.settings.future_sections import (
    future_sections as fs_setting_form,
)


class LocationSchemaTests(SimpleTestCase):
    def test_location_is_an_available_field(self):
        self.assertIn(
            'location',
            TeachingSectionFieldSchema.get_available_field_names())

    def test_location_meta_is_a_select_with_label(self):
        meta = TeachingSectionFieldSchema.get_field_meta('location')
        self.assertEqual(meta.get('widget_type'), 'select')
        self.assertEqual(meta.get('default_label'), 'Location')

    def test_make_field_is_a_choicefield_with_provided_choices_when_visible(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'location', visible=True,
            choices=[('Room A', 'Room A'), ('Room B', 'Room B')])
        self.assertIsInstance(field, forms.ChoiceField)
        self.assertEqual(field.choices[0], ('', '---------'))
        self.assertIn(('Room A', 'Room A'), field.choices)

    def test_make_field_is_hidden_when_not_visible(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'location', visible=False)
        self.assertIsInstance(field.widget, forms.HiddenInput)


class LocationSettingFieldTests(SimpleTestCase):
    def test_location_options_field_is_declared(self):
        self.assertIn('location_options', fs_setting_form.base_fields)

    def test_location_options_field_is_optional(self):
        self.assertFalse(
            fs_setting_form.base_fields['location_options'].required)
