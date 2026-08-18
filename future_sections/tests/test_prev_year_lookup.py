from django.test import TestCase

from cis.models.course import Course, Cohort
from cis.models.highschool import HighSchool
from cis.models.section import ClassSection
from cis.models.term import AcademicYear, Term

from ..utils import build_prev_year_lookup


class PrevYearLookupTests(TestCase):
    """Previous-year section counts feed the 'Previous Year' column in both
    the HS admin and CE portals.

    ClassSection.CLASS_STATUS is (('A', 'Active'), ('C', 'Cancelled')) — the
    stored values are the single-letter codes, not the labels.
    """

    @classmethod
    def setUpTestData(cls):
        cls.prev_ay = AcademicYear.objects.create(name='2026-2027')
        cls.other_ay = AcademicYear.objects.create(name='2027-2028')
        cls.term = Term.objects.create(
            academic_year=cls.prev_ay, code='202640',
            label='Fall CiHS Trimester 202640',
        )
        cls.spring = Term.objects.create(
            academic_year=cls.prev_ay, code='202650', label='Spring 202650',
        )
        cls.other_term = Term.objects.create(
            academic_year=cls.other_ay, code='202740', label='Fall 202740',
        )
        cohort = Cohort.objects.create(name='Default Cohort', designator='DC')
        cls.course = Course.objects.create(
            name='PHED125', title='Physical Education 125',
            catalog_number='125', cohort=cohort, credit_hours=3,
        )
        cls.hs = HighSchool.objects.create(name='Zillah High School')

    def _section(self, number, term=None, status='A', course=None, hs=None):
        return ClassSection.objects.create(
            class_number=number, section_number='A',
            term=term or self.term,
            course=course or self.course,
            highschool=hs or self.hs,
            status=status,
        )

    def _key(self):
        return f'{self.course.id}_{self.hs.id}'

    def test_section_is_counted(self):
        self._section('1001')
        lookup = build_prev_year_lookup(str(self.prev_ay.id), ['A'])
        self.assertEqual(
            lookup.get(self._key()),
            [{'term_name': 'Fall CiHS Trimester 202640', 'count': 1}])

    def test_multiple_sections_in_one_term_are_summed(self):
        self._section('1001')
        self._section('1002')
        lookup = build_prev_year_lookup(str(self.prev_ay.id), ['A'])
        self.assertEqual(lookup[self._key()],
                         [{'term_name': 'Fall CiHS Trimester 202640',
                           'count': 2}])

    def test_each_term_gets_its_own_entry(self):
        self._section('1001')
        self._section('2001', term=self.spring)
        lookup = build_prev_year_lookup(str(self.prev_ay.id), ['A'])
        by_term = {e['term_name']: e['count'] for e in lookup[self._key()]}
        self.assertEqual(by_term, {'Fall CiHS Trimester 202640': 1,
                                   'Spring 202650': 1})

    def test_other_academic_years_are_excluded(self):
        self._section('9001', term=self.other_term)
        lookup = build_prev_year_lookup(str(self.prev_ay.id), ['A'])
        self.assertEqual(lookup, {})

    def test_no_previous_academic_year_returns_empty(self):
        self._section('1001')
        self.assertEqual(build_prev_year_lookup(None, ['A']), {})
        self.assertEqual(build_prev_year_lookup('', ['A']), {})

    def test_key_is_course_id_underscore_highschool_id(self):
        self._section('1001')
        other_hs = HighSchool.objects.create(name='Other High School')
        self._section('1003', hs=other_hs)
        lookup = build_prev_year_lookup(str(self.prev_ay.id), ['A'])
        self.assertIn(f'{self.course.id}_{self.hs.id}', lookup)
        self.assertIn(f'{self.course.id}_{other_hs.id}', lookup)


class PrevYearStatusFilterTests(PrevYearLookupTests):
    """The statuses counted come from the `prev_year_class_status` setting —
    nothing is hardcoded to 'A'/'Active'."""

    def test_only_selected_statuses_are_counted(self):
        self._section('1001', status='A')
        self._section('1002', status='C')
        lookup = build_prev_year_lookup(str(self.prev_ay.id), ['A'])
        self.assertEqual(lookup[self._key()][0]['count'], 1)

    def test_a_different_status_can_be_selected_instead(self):
        self._section('1001', status='A')
        self._section('1002', status='C')
        lookup = build_prev_year_lookup(str(self.prev_ay.id), ['C'])
        self.assertEqual(lookup[self._key()][0]['count'], 1)

    def test_several_statuses_can_be_selected_together(self):
        self._section('1001', status='A')
        self._section('1002', status='C')
        lookup = build_prev_year_lookup(str(self.prev_ay.id), ['A', 'C'])
        self.assertEqual(lookup[self._key()][0]['count'], 2)

    def test_status_not_present_in_the_data_yields_nothing(self):
        self._section('1001', status='A')
        lookup = build_prev_year_lookup(str(self.prev_ay.id), ['C'])
        self.assertEqual(lookup, {})

    def test_empty_selection_counts_every_status(self):
        self._section('1001', status='A')
        self._section('1002', status='C')
        for unset in ([], None):
            lookup = build_prev_year_lookup(str(self.prev_ay.id), unset)
            self.assertEqual(lookup[self._key()][0]['count'], 2, unset)

    def test_omitting_the_argument_counts_every_status(self):
        self._section('1001', status='A')
        self._section('1002', status='C')
        lookup = build_prev_year_lookup(str(self.prev_ay.id))
        self.assertEqual(lookup[self._key()][0]['count'], 2)


class PrevYearStatusSettingTests(TestCase):
    def test_setting_field_is_declared_and_optional(self):
        from ..settings.future_sections import (
            future_sections as FSForm,
        )
        field = FSForm.base_fields['prev_year_class_status']
        self.assertFalse(field.required)

    def test_setting_choices_come_from_the_model(self):
        from ..settings.future_sections import (
            future_sections as FSForm,
        )
        field = FSForm.base_fields['prev_year_class_status']
        self.assertEqual(list(field.choices), list(ClassSection.CLASS_STATUS))
