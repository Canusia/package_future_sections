"""The two course-type fields belong to the Add Teacher form.

"Type of course" (`course_type`) and "This is a:" (`course_request_type`) are
only asked when a new teacher is being added, so `add_teacher_form_config`
drives them and the ordinary teaching form never renders them. Options come
from the `course_types` / `course_request_types` settings as pipe-delimited
value:Label pairs. A field with no configured options is not rendered at all —
without that rule, a tenant taking this release would get an empty and
by-default-required dropdown it cannot satisfy.
"""
import json

from django import forms as djforms
from django.contrib.auth.models import Group
from django.test import RequestFactory, SimpleTestCase, TestCase

from cis.models.course import Campus, Cohort, Course
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.term import AcademicYear

from ..forms import (
    AddNewTeacherForm, TeacherCourseSectionForm,
)
from ..schemas import TeachingSectionFieldSchema


COURSE_TYPES = 'dual:Dual Credit|cpl:Credit for Prior Learning (CPL)'
COURSE_REQUEST_TYPES = 'new:New Course|new_instructor:With a new instructor'


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

    def test_they_are_declared_add_teacher_only(self):
        self.assertEqual(
            set(TeacherCourseSectionForm.ADD_TEACHER_ONLY_FIELDS),
            {'course_type', 'course_request_type'})


class TeachingFormExclusionTests(TestCase):
    """The plain teaching form never renders them, whatever it is told."""

    def _make_setting(self):
        # Both fields listed as visible AND required in the teaching config —
        # the configuration that used to render them there.
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': ['term', 'course_type', 'course_request_type'],
                    'required': ['term', 'course_type',
                                 'course_request_type'],
                }),
                'course_types': COURSE_TYPES,
                'course_request_types': COURSE_REQUEST_TYPES,
            },
        )

    def test_fields_are_hidden_even_when_the_teaching_config_lists_them(self):
        self._make_setting()
        form = TeacherCourseSectionForm()
        for name in ('course_type', 'course_request_type'):
            self.assertIsInstance(
                form.fields[name].widget, djforms.HiddenInput, name)

    def test_fields_are_not_required_on_the_teaching_form(self):
        self._make_setting()
        form = TeacherCourseSectionForm()
        for name in ('course_type', 'course_request_type'):
            self.assertFalse(form.fields[name].required, name)


def _hs_admin_user():
    Group.objects.get_or_create(name='highschool_admin')
    u = CustomUser.objects.create(
        username='hsa-ct@x.com', email='hsa-ct@x.com', is_active=True)
    u.groups.add(Group.objects.get(name='highschool_admin'))
    return u


class AddTeacherCourseTypeTests(TestCase):
    """`add_teacher_form_config` drives both selects on the Add Teacher form."""

    @classmethod
    def setUpTestData(cls):
        from cis.models.highschool import HighSchool
        from cis.models.highschool_administrator import (
            HSAdministrator, HSAdministratorPosition, HSPosition,
        )

        cls.user = _hs_admin_user()
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Stocked', code='S')
        Course.objects.create(
            name='A1', title='Alpha Active', cohort=cls.cohort,
            catalog_number='101', credit_hours=3, campus=cls.campus,
            status='Active')

        highschool = HighSchool.objects.create(name='Test HS')
        position = HSPosition.objects.create(name='Coordinator')
        hsadmin = HSAdministrator.objects.create(user=cls.user)
        HSAdministratorPosition.objects.create(
            hsadmin=hsadmin, highschool=highschool, position=position,
            status='Active')

    def _make_setting(self, fields=('course_type', 'course_request_type'),
                      required=(), labels=None,
                      course_types=COURSE_TYPES,
                      course_request_types=COURSE_REQUEST_TYPES):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'add_teacher_form_config': json.dumps({
                    'fields': list(fields),
                    'required': list(required),
                    'labels': labels or {},
                }),
                # Deliberately empty: the teaching config must have no say.
                'teaching_form_config': json.dumps({'fields': ['term']}),
                'course_types': course_types,
                'course_request_types': course_request_types,
            },
        )

    def _form(self, **kwargs):
        req = RequestFactory().get('/')
        req.user = self.user
        return AddNewTeacherForm(req, self.ay, 'pathways', **kwargs)

    def test_configured_field_renders_as_a_select_with_its_options(self):
        self._make_setting()
        form = self._form()
        self.assertIsInstance(
            form.fields['course_type'].widget, djforms.Select)
        choices = dict(form.fields['course_type'].choices)
        self.assertEqual(choices.get('dual'), 'Dual Credit')
        self.assertEqual(
            choices.get('cpl'), 'Credit for Prior Learning (CPL)')

    def test_field_left_out_of_the_config_is_hidden(self):
        self._make_setting(fields=('course_type',))
        form = self._form()
        self.assertIsInstance(
            form.fields['course_request_type'].widget, djforms.HiddenInput)
        self.assertFalse(form.fields['course_request_type'].required)

    def test_required_comes_from_the_add_teacher_config(self):
        self._make_setting(required=('course_type',))
        form = self._form()
        self.assertTrue(form.fields['course_type'].required)
        self.assertFalse(form.fields['course_request_type'].required)

    def test_custom_label_comes_from_the_add_teacher_config(self):
        self._make_setting(labels={'course_type': 'What kind of course?'})
        form = self._form()
        self.assertEqual(
            form.fields['course_type'].label, 'What kind of course?')

    def test_unconfigured_options_hide_the_field_even_if_visible(self):
        # Listed as visible and required, but no options to pick from.
        self._make_setting(required=('course_type',), course_types='')
        form = self._form()
        self.assertIsInstance(
            form.fields['course_type'].widget, djforms.HiddenInput)
        self.assertFalse(form.fields['course_type'].required)

    def test_the_other_field_is_unaffected_by_an_empty_list(self):
        self._make_setting(course_types='')
        form = self._form()
        choices = dict(form.fields['course_request_type'].choices)
        self.assertEqual(choices.get('new'), 'New Course')

    def test_stored_value_no_longer_configured_stays_selectable(self):
        self._make_setting()
        form = self._form(initial={'course_type': 'retired_option'})
        self.assertIn(
            'retired_option', dict(form.fields['course_type'].choices))


class AddTeacherCourseTypePersistenceTests(TestCase):
    """The two answers must survive `AddNewTeacherForm.save()`.

    They are collected on the Add Teacher form but the saved section payload
    is hand-built, so a field that is not explicitly copied is silently
    discarded — the user picks a value and nothing records it.
    """

    @classmethod
    def setUpTestData(cls):
        from cis.models.highschool import HighSchool
        from cis.models.highschool_administrator import (
            HSAdministrator, HSAdministratorPosition, HSPosition,
        )
        from cis.models.term import Term

        Group.objects.get_or_create(name='instructor')
        cls.user = _hs_admin_user()
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

    def setUp(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'academic_year': str(self.ay.id),
                'add_teacher_form_config': json.dumps({
                    'fields': ['course_type', 'course_request_type'],
                    'required': [],
                    'labels': {},
                }),
                'teaching_form_config': json.dumps({'fields': ['term']}),
                'course_types': COURSE_TYPES,
                'course_request_types': COURSE_REQUEST_TYPES,
            },
        )

    def _saved_record(self, **overrides):
        req = RequestFactory().post('/')
        req.user = self.user
        data = {
            'action': 'add_new_teacher',
            'academic_year_id': str(self.ay.id),
            'highschool': str(self.highschool.id),
            'term': str(self.term.id),
            'course': str(self.course.id),
            'teacher_first_name': 'Ada',
            'teacher_last_name': 'Lovelace',
            'teacher_email': 'ada@example.com',
            'course_type': 'dual',
            'course_request_type': 'new',
        }
        data.update(overrides)
        form = AddNewTeacherForm(req, self.ay, 'pathways', data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        return form.save(req, self.ay)

    def _saved_section(self, **overrides):
        return self._saved_record(**overrides).section_info['sections'][-1]

    def test_course_type_is_stored_on_the_saved_section(self):
        self.assertEqual(self._saved_section()['course_type'], 'dual')

    def test_course_request_type_is_stored_on_the_saved_section(self):
        self.assertEqual(
            self._saved_section()['course_request_type'], 'new')

    def test_section_display_shows_the_configured_labels(self):
        """End to end: the saved code renders as its label in the table."""
        setting = Setting.objects.get(key='cis_future_sections')
        setting.value['teaching_form_config'] = json.dumps({
            'fields': ['term'],
            'display_template': '{course_type} | {course_request_type}',
        })
        setting.save()

        record = self._saved_record()
        self.assertEqual(
            record.section_display[-1], 'Dual Credit | New Course')


class ChoiceLabelMapTests(SimpleTestCase):
    """Stored values are opaque codes; the section display wants the label."""

    def test_map_is_built_for_both_choice_backed_fields(self):
        from ..utils import build_section_choice_labels
        labels = build_section_choice_labels({
            'course_types': COURSE_TYPES,
            'course_request_types': COURSE_REQUEST_TYPES,
        })
        self.assertEqual(labels['course_type']['dual'], 'Dual Credit')
        self.assertEqual(
            labels['course_request_type']['new_instructor'],
            'With a new instructor')

    def test_unconfigured_setting_yields_an_empty_map(self):
        from ..utils import build_section_choice_labels
        labels = build_section_choice_labels({'course_types': ''})
        self.assertEqual(labels['course_type'], {})


class ChoiceLabelDisplayTests(SimpleTestCase):

    def test_stored_value_renders_as_its_configured_label(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'course_type': 'dual'}, '{course_type}',
            choice_labels={'course_type': {'dual': 'Dual Credit'}})
        self.assertEqual(out, 'Dual Credit')

    def test_value_missing_from_the_map_falls_back_to_the_raw_value(self):
        # A retired option must still say something rather than vanish.
        out = TeachingSectionFieldSchema.format_section_display(
            {'course_type': 'retired'}, '{course_type}',
            choice_labels={'course_type': {'dual': 'Dual Credit'}})
        self.assertEqual(out, 'retired')

    def test_label_is_escaped(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'course_type': 'x'}, '{course_type}',
            choice_labels={'course_type': {'x': '<b>Dual</b>'}})
        self.assertNotIn('<b>', out)


class ExportChoiceLabelTests(TestCase):
    """The CSV export writes values through `get_by_property`.

    Its headers are human-readable labels, so its cells must be too — a
    column of `dual` is not something a CE admin can hand to anyone.
    """

    def setUp(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'course_types': COURSE_TYPES,
                'course_request_types': COURSE_REQUEST_TYPES,
            },
        )

    def _record(self, **section):
        from ..models import FutureCourse
        return FutureCourse(section_info={'sections': [section]})

    def test_choice_value_is_exported_as_its_label(self):
        record = self._record(course_type='cpl')
        self.assertEqual(
            record.get_by_property(0, 'course_type'),
            'Credit for Prior Learning (CPL)')

    def test_retired_value_is_exported_as_itself(self):
        record = self._record(course_type='retired')
        self.assertEqual(
            record.get_by_property(0, 'course_type'), 'retired')

    def test_ordinary_field_is_untouched(self):
        record = self._record(class_period='3rd')
        self.assertEqual(
            record.get_by_property(0, 'class_period'), '3rd')

    def test_missing_value_stays_empty(self):
        record = self._record(course_type='')
        self.assertEqual(record.get_by_property(0, 'course_type'), '')


class ExportColumnTests(TestCase):
    """The export columns come from settings, and these two live on the
    Add Teacher config — the teaching-form builder deliberately does not
    offer them, so reading only that config leaves them out entirely."""

    def _make_setting(self, at_fields=('course_type', 'course_request_type'),
                      at_labels=None, teaching_fields=('term',)):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps(
                    {'fields': list(teaching_fields)}),
                'add_teacher_form_config': json.dumps({
                    'fields': list(at_fields),
                    'labels': at_labels or {},
                }),
                'course_types': COURSE_TYPES,
                'course_request_types': COURSE_REQUEST_TYPES,
            },
        )

    def _record(self):
        from ..models import FutureCourse
        return FutureCourse(section_info={'sections': []})

    def test_configured_add_teacher_fields_become_export_columns(self):
        self._make_setting()
        self.assertEqual(
            self._record().additional_fields(),
            ['term', 'course_type', 'course_request_type'])

    def test_field_not_on_the_add_teacher_form_is_not_exported(self):
        self._make_setting(at_fields=('course_type',))
        self.assertNotIn(
            'course_request_type', self._record().additional_fields())

    def test_a_field_is_not_duplicated_when_both_configs_list_it(self):
        self._make_setting(teaching_fields=('term', 'course_type'))
        self.assertEqual(
            self._record().additional_fields().count('course_type'), 1)

    def test_export_header_uses_the_schema_label(self):
        from ..models import FutureCourse
        self._make_setting()
        self.assertEqual(
            FutureCourse.get_export_labels()['course_type'],
            'Type of course')

    def test_export_header_honours_the_add_teacher_label_override(self):
        from ..models import FutureCourse
        self._make_setting(at_labels={'course_type': 'Credit Type'})
        self.assertEqual(
            FutureCourse.get_export_labels()['course_type'], 'Credit Type')
