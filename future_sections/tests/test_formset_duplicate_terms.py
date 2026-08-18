"""Two rows may share a term.

Pre-population emits one row per previous-year section, so a teacher with two
sections in one term opens the modal with two rows carrying the same term.
The formset has always accepted that — its "Terms must be unique" branch was
unreachable dead code — and this pins the behaviour now that the feature
depends on it.
"""
import json

from django.forms import formset_factory
from django.test import TestCase

from cis.models.settings import Setting
from cis.models.term import AcademicYear, Term

from ..forms import TeacherCourseBaseLinkFormSet, TeacherCourseSectionForm


class DuplicateTermsAreAllowedTests(TestCase):

    def setUp(self):
        self.academic_year = AcademicYear.objects.create(name='2026-2027')
        self.term = Term.objects.create(
            code='SP26', label='Spring Credit 2026',
            academic_year=self.academic_year)
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'academic_year': str(self.academic_year.id),
                'teaching_form_config': json.dumps({
                    'fields': ['term', 'section_number'],
                    'required': ['term'],
                }),
            },
        )

    def _formset(self, data):
        TeachingFormSet = formset_factory(
            TeacherCourseSectionForm,
            formset=TeacherCourseBaseLinkFormSet,
            extra=0,
        )
        return TeachingFormSet(data)

    def test_two_rows_in_the_same_term_validate(self):
        formset = self._formset({
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-term': str(self.term.id),
            'form-0-section_number': 'DC030',
            'form-1-term': str(self.term.id),
            'form-1-section_number': 'DC040',
        })
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_no_rows_at_all_is_still_rejected(self):
        formset = self._formset({
            'form-TOTAL_FORMS': '0',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
        })
        self.assertFalse(formset.is_valid())
        self.assertIn(
            'Please enter at least 1 section information',
            str(formset.non_form_errors()))
