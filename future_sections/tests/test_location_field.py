import json

from django import forms
from django.test import SimpleTestCase, TestCase

from cis.models.settings import Setting
from ..forms import TeacherCourseSectionForm
from ..schemas import TeachingSectionFieldSchema
from ..settings.future_sections import (
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


class LocationFormWiringTests(TestCase):
    def _make_setting(self, location_options='Main Campus|North High|Online',
                      fields=('term', 'location')):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': list(fields),
                    'required': ['term'],
                }),
                'location_options': location_options,
            },
        )

    def test_location_is_choicefield_with_configured_options_when_visible(self):
        self._make_setting()
        form = TeacherCourseSectionForm()
        field = form.fields['location']
        from django import forms as djforms
        self.assertIsInstance(field, djforms.ChoiceField)
        self.assertEqual(field.choices[0], ('', '---------'))
        self.assertIn(('Main Campus', 'Main Campus'), field.choices)
        self.assertIn(('Online', 'Online'), field.choices)

    def test_location_is_hidden_when_not_enabled(self):
        self._make_setting(fields=('term',))
        form = TeacherCourseSectionForm()
        from django import forms as djforms
        self.assertIsInstance(form.fields['location'].widget, djforms.HiddenInput)

    def test_stored_location_not_in_options_is_preserved(self):
        self._make_setting(location_options='Main Campus|Online')
        form = TeacherCourseSectionForm(initial={'location': 'Legacy Room'})
        values = {c[0] for c in form.fields['location'].choices}
        self.assertIn('Legacy Room', values)
