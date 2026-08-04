import json

from django.test import TestCase

from cis.models.settings import Setting
from cis.models.term import AcademicYear, Term
from future_sections.future_sections.forms import TeacherCourseSectionForm


class _DateFormMixin:
    def _make_setting(self, fields=('term', 'start_date', 'end_date')):
        self.academic_year = AcademicYear.objects.create(name='2026-2027')
        self.term = Term.objects.create(
            code='FA26', label='Fall 2026', academic_year=self.academic_year)
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'academic_year': str(self.academic_year.id),
                'teaching_form_config': json.dumps({
                    'fields': list(fields),
                    'required': ['term'],
                }),
            },
        )

    def _bind(self, **data):
        payload = {'term': str(self.term.id)}
        payload.update(data)
        return TeacherCourseSectionForm(data=payload)


class DateOrderingTests(_DateFormMixin, TestCase):
    def test_end_before_start_is_rejected(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01', end_date='2026-08-01')
        self.assertFalse(form.is_valid())
        self.assertIn('end_date', form.errors)

    def test_end_equal_to_start_is_accepted(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01', end_date='2026-09-01')
        self.assertTrue(form.is_valid(), form.errors)

    def test_end_after_start_is_accepted(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01', end_date='2027-05-30')
        self.assertTrue(form.is_valid(), form.errors)

    def test_only_start_supplied_is_accepted(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01')
        self.assertTrue(form.is_valid(), form.errors)

    def test_only_end_supplied_is_accepted(self):
        self._make_setting()
        form = self._bind(end_date='2026-09-01')
        self.assertTrue(form.is_valid(), form.errors)

    def test_neither_supplied_is_accepted(self):
        self._make_setting()
        form = self._bind()
        self.assertTrue(form.is_valid(), form.errors)

    def test_hidden_date_fields_impose_no_ordering_constraint(self):
        self._make_setting(fields=('term',))
        form = self._bind(start_date='2026-09-01', end_date='2026-08-01')
        self.assertTrue(form.is_valid(), form.errors)


class DateSerializationTests(_DateFormMixin, TestCase):
    def test_cleaned_dates_are_iso_strings(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01', end_date='2027-05-30')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['start_date'], '2026-09-01')
        self.assertEqual(form.cleaned_data['end_date'], '2027-05-30')

    def test_cleaned_data_is_json_serializable(self):
        self._make_setting()
        form = self._bind(start_date='2026-09-01', end_date='2027-05-30')
        self.assertTrue(form.is_valid(), form.errors)
        data = dict(form.cleaned_data)
        data.pop('syllabus', None)
        json.dumps(data)  # must not raise

    def test_us_format_input_is_normalized_to_iso(self):
        self._make_setting()
        form = self._bind(start_date='09/01/2026')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['start_date'], '2026-09-01')

    def test_empty_date_stays_empty(self):
        self._make_setting()
        form = self._bind(start_date='')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn(form.cleaned_data['start_date'], (None, ''))
