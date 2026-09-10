"""Two upload fields asked only when a new teacher is being added.

`new_teacher_syllabus` and `new_teacher_class_assessment` are deliberately
separate from the teaching form's `syllabus` and `assessment_upload`: a
tenant may collect documents in both places, and the two sets must not
share a storage key or a configuration entry.
"""
import json

from crispy_forms.utils import render_crispy_form
from django import forms as djforms
from django.contrib.auth.models import Group
from django.test import RequestFactory, SimpleTestCase, TestCase

from cis.models.course import Campus, Cohort, Course
from cis.models.customuser import CustomUser
from cis.models.highschool import HighSchool
from cis.models.highschool_administrator import (
    HSAdministrator, HSAdministratorPosition, HSPosition,
)
from cis.models.settings import Setting
from cis.models.term import AcademicYear, Term
from ..forms import AddNewTeacherForm, TeacherCourseSectionForm
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


class _AddTeacherFixture:
    """Minimum graph for constructing AddNewTeacherForm as an HS admin."""

    @classmethod
    def setUpTestData(cls):
        Group.objects.get_or_create(name='highschool_admin')
        cls.user = CustomUser.objects.create(
            username='hsa-upload@x.com', email='hsa-upload@x.com',
            is_active=True)
        cls.user.groups.add(Group.objects.get(name='highschool_admin'))

        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.term = Term.objects.create(
            label='Fall 2099', code='F99', academic_year=cls.ay)
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Stocked', code='S')
        cls.course = Course.objects.create(
            name='A1', title='Alpha Active', cohort=cls.cohort,
            catalog_number='101', credit_hours=3, campus=cls.campus,
            status='Active')

        cls.highschool = HighSchool.objects.create(name='Test HS')
        position = HSPosition.objects.create(name='Coordinator')
        hsadmin = HSAdministrator.objects.create(user=cls.user)
        HSAdministratorPosition.objects.create(
            hsadmin=hsadmin, highschool=cls.highschool, position=position,
            status='Active')

    def _make_setting(self, fields=NEW_UPLOAD_FIELDS, required=(),
                      labels=None, help_texts=None):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'academic_year': str(self.ay.id),
                'add_teacher_form_config': json.dumps({
                    'fields': list(fields),
                    'required': list(required),
                    'labels': labels or {},
                    'help_texts': help_texts or {},
                }),
                # Deliberately bare: the teaching config must have no say.
                'teaching_form_config': json.dumps({'fields': ['term']}),
            },
        )

    def _form(self, **kwargs):
        req = RequestFactory().get('/')
        req.user = self.user
        return AddNewTeacherForm(req, self.ay, 'pathways', **kwargs)


class AddTeacherUploadRenderTests(_AddTeacherFixture, TestCase):

    def test_configured_field_renders_as_a_file_input(self):
        self._make_setting()
        form = self._form()
        for name in NEW_UPLOAD_FIELDS:
            self.assertIsInstance(form.fields[name], djforms.FileField, name)
            self.assertIsInstance(
                form.fields[name].widget, djforms.ClearableFileInput, name)

    def test_field_left_out_of_the_config_stays_hidden(self):
        self._make_setting(fields=('new_teacher_syllabus',))
        form = self._form()
        self.assertIsInstance(
            form.fields['new_teacher_syllabus'], djforms.FileField)
        self.assertIsInstance(
            form.fields['new_teacher_class_assessment'].widget,
            djforms.HiddenInput)
        self.assertFalse(
            form.fields['new_teacher_class_assessment'].required)

    def test_required_comes_from_the_add_teacher_config(self):
        self._make_setting(required=('new_teacher_syllabus',))
        form = self._form()
        self.assertTrue(form.fields['new_teacher_syllabus'].required)
        self.assertFalse(
            form.fields['new_teacher_class_assessment'].required)

    def test_required_is_ignored_for_a_field_that_is_not_visible(self):
        # Nobody can satisfy a required field that is not rendered.
        self._make_setting(fields=(), required=NEW_UPLOAD_FIELDS)
        form = self._form()
        for name in NEW_UPLOAD_FIELDS:
            self.assertFalse(form.fields[name].required, name)

    def test_custom_label_and_help_text_survive_the_rebuild(self):
        self._make_setting(
            labels={'new_teacher_syllabus': 'Course Syllabus (PDF)'},
            help_texts={'new_teacher_syllabus': 'One file, max 10MB'})
        form = self._form()
        self.assertEqual(
            form.fields['new_teacher_syllabus'].label,
            'Course Syllabus (PDF)')
        self.assertEqual(
            form.fields['new_teacher_syllabus'].help_text,
            'One file, max 10MB')

    def test_default_label_is_used_when_no_override_is_configured(self):
        self._make_setting()
        form = self._form()
        self.assertEqual(form.fields['new_teacher_syllabus'].label,
                         'Syllabus')
        self.assertEqual(
            form.fields['new_teacher_class_assessment'].label,
            'Class Assessment')

    def test_no_config_at_all_leaves_both_hidden(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={'academic_year': str(self.ay.id)},
        )
        form = self._form()
        for name in NEW_UPLOAD_FIELDS:
            self.assertIsInstance(
                form.fields[name].widget, djforms.HiddenInput, name)
