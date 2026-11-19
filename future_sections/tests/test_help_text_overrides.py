"""Teaching Form / Add Teacher Form help text (#14).

CE edits a field's help text from the settings page (saved to
``help_texts`` in the form config) and can clear a default help text. A
missing key means "use the default"; an explicit "" means "show none".
"""
import json
import os

from django.test import RequestFactory, SimpleTestCase, TestCase

from crispy_forms.utils import render_crispy_form

from cis.models.customuser import CustomUser
from cis.models.settings import Setting

from ..forms import TeacherCourseSectionForm
from ..schemas import TeachingSectionFieldSchema
from ..settings.future_sections import future_sections

CLASS_PERIOD_DEFAULT = 'e.g., 1st period, 2nd hour'


class SchemaHelpTextOverrideTests(SimpleTestCase):
    def test_no_override_uses_default(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'class_period', visible=True)
        self.assertEqual(field.help_text, CLASS_PERIOD_DEFAULT)

    def test_empty_override_clears_default(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'class_period', visible=True, help_text_override='')
        self.assertEqual(field.help_text, '')

    def test_override_replaces_default(self):
        field = TeachingSectionFieldSchema.make_django_form_field(
            'class_period', visible=True,
            help_text_override='Example: 11:01 a.m. - 12:22 p.m.')
        self.assertEqual(field.help_text, 'Example: 11:01 a.m. - 12:22 p.m.')


class TeachingFormHelpTextTests(TestCase):
    def _form(self, help_texts):
        Setting.objects.create(key='cis_future_sections', value={
            'teaching_form_config': json.dumps({
                'fields': ['term', 'class_period'],
                'required': ['term'],
                'help_texts': help_texts,
            }),
        })
        return TeacherCourseSectionForm()

    def test_saved_help_text_is_used(self):
        form = self._form({'class_period': 'Example: 11:01 a.m. - 12:22 p.m.'})
        self.assertEqual(form.fields['class_period'].help_text,
                         'Example: 11:01 a.m. - 12:22 p.m.')

    def test_saved_empty_help_text_clears_default(self):
        form = self._form({'class_period': ''})
        self.assertEqual(form.fields['class_period'].help_text, '')

    def test_absent_key_keeps_default(self):
        form = self._form({})
        self.assertEqual(form.fields['class_period'].help_text,
                         CLASS_PERIOD_DEFAULT)


class SettingsCardHelpTextColumnTests(TestCase):
    def setUp(self):
        user = CustomUser.objects.create(
            username='ce-help@x.com', email='ce-help@x.com', is_active=True)
        request = RequestFactory().get(
            '/?report_id=0f4e3b1a-1111-2222-3333-444455556666')
        request.user = user
        self.html = render_crispy_form(future_sections(request))

    def test_teaching_rows_have_help_input_with_default_placeholder(self):
        self.assertIn('class="form-control form-control-sm tfc-help" '
                      f'data-field="class_period" placeholder="{CLASS_PERIOD_DEFAULT}"',
                      self.html)
        self.assertIn('tfc-help-none', self.html)

    def test_add_teacher_rows_have_help_input(self):
        self.assertIn('atfc-help" data-field="teacher_email"', self.html)
        self.assertIn('atfc-help-none', self.html)


class SettingsJsHelpTextTests(SimpleTestCase):
    def test_js_saves_help_texts_from_the_ui(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'staticfiles', 'future_sections', 'js', 'settings.js')
        with open(path, encoding='utf-8') as f:
            js = f.read()
        self.assertNotIn('not exposed in UI', js)
        self.assertEqual(js.count("collectHelpTexts($ui, '"), 2)
        self.assertEqual(js.count("populateHelpTexts($ui, '"), 2)


class LegacyAndNonSchemaHelpTextTests(TestCase):
    def _form(self, help_texts, legacy=None):
        value = {'teaching_form_config': json.dumps({
            'fields': ['term', 'class_period'], 'required': ['term'],
            'help_texts': help_texts,
        })}
        if legacy is not None:
            value['form_field_messages'] = json.dumps(legacy)
        Setting.objects.create(key='cis_future_sections', value=value)
        return TeacherCourseSectionForm()

    def test_help_texts_beat_legacy_form_field_messages(self):
        form = self._form({'class_period': 'New'},
                          legacy={'class_period': {'help_text': 'Legacy'}})
        self.assertEqual(form.fields['class_period'].help_text, 'New')

    def test_no_help_text_beats_legacy_form_field_messages(self):
        form = self._form({'class_period': ''},
                          legacy={'class_period': {'help_text': 'Legacy'}})
        self.assertEqual(form.fields['class_period'].help_text, '')

    def test_legacy_still_applies_without_a_help_texts_key(self):
        form = self._form({}, legacy={'class_period': {'help_text': 'Legacy'}})
        self.assertEqual(form.fields['class_period'].help_text, 'Legacy')

    def test_term_help_text_can_be_cleared(self):
        form = self._form({'term': ''})
        self.assertEqual(form.fields['term'].help_text, '')


class AddTeacherHelpTextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Group
        from cis.models.term import AcademicYear
        Group.objects.get_or_create(name='highschool_admin')
        cls.user = CustomUser.objects.create(
            username='hsa-help@x.com', email='hsa-help@x.com', is_active=True)
        cls.user.groups.add(Group.objects.get(name='highschool_admin'))
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        from cis.models.highschool import HighSchool
        from cis.models.highschool_administrator import (
            HSAdministrator, HSAdministratorPosition, HSPosition,
        )
        hs = HighSchool.objects.create(name='Help HS')
        HSAdministratorPosition.objects.create(
            hsadmin=HSAdministrator.objects.create(user=cls.user),
            highschool=hs, position=HSPosition.objects.create(name='Coord'),
            status='Active')

    def _form(self, help_texts):
        from ..forms import AddNewTeacherForm
        Setting.objects.create(key='cis_future_sections', value={
            'academic_year': str(self.ay.id),
            'add_teacher_form_config': json.dumps({
                'fields': ['teacher_email', 'new_teacher_syllabus'],
                'required': [], 'help_texts': help_texts,
            }),
            'teaching_form_config': json.dumps({'fields': ['term']}),
        })
        req = RequestFactory().get('/')
        req.user = self.user
        return AddNewTeacherForm(req, self.ay, 'pathways')

    def test_add_teacher_only_file_field_help_text_override(self):
        form = self._form({'new_teacher_syllabus': 'PDF, under 5 MB'})
        self.assertEqual(form.fields['new_teacher_syllabus'].help_text,
                         'PDF, under 5 MB')

    def test_add_teacher_only_field_empty_override_passes_through(self):
        from unittest import mock
        real = TeachingSectionFieldSchema.get_field_meta.__func__

        def with_default(cls, name):
            meta = dict(real(cls, name))
            meta['default_help_text'] = 'Schema default'
            return meta
        with mock.patch.object(TeachingSectionFieldSchema, 'get_field_meta',
                               classmethod(with_default)):
            self.assertEqual(
                self._form({'new_teacher_syllabus': ''})
                .fields['new_teacher_syllabus'].help_text, '')
            Setting.objects.all().delete()
            self.assertEqual(
                self._form({}).fields['new_teacher_syllabus'].help_text,
                'Schema default')

    def test_declared_teacher_field_help_text_override(self):
        form = self._form({'teacher_email': 'Use the school address'})
        self.assertEqual(form.fields['teacher_email'].help_text,
                         'Use the school address')
