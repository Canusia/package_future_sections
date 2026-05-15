from django.http import QueryDict
from django.test import TestCase, RequestFactory

from cis.models.term import AcademicYear, Term

from future_sections.future_sections.settings.future_sections import (
    future_sections as FSForm,
)


def _qdict(pairs):
    qd = QueryDict(mutable=True)
    for k, v in pairs:
        if isinstance(v, (list, tuple)):
            for vv in v:
                qd.appendlist(k, vv)
        else:
            qd[k] = v
    return qd


class CycleTermsValidationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get('/?report_id=1')
        self.ay_a = AcademicYear.objects.create(name='2026-2027')
        self.ay_b = AcademicYear.objects.create(name='2027-2028')
        self.fall_a = Term.objects.create(
            code='FA26', label='Fall 2026', academic_year=self.ay_a)
        self.spring_a = Term.objects.create(
            code='SP27', label='Spring 2027', academic_year=self.ay_a)
        self.fall_b = Term.objects.create(
            code='FA27', label='Fall 2027', academic_year=self.ay_b)

    def test_cycle_terms_required(self):
        data = _qdict([('cycle_terms', [])])
        form = FSForm(self.request, data=data)
        form.is_valid()
        self.assertIn('cycle_terms', form.errors)

    def test_cycle_terms_must_share_ay(self):
        data = _qdict([
            ('cycle_terms', [str(self.fall_a.id), str(self.fall_b.id)]),
        ])
        form = FSForm(self.request, data=data)
        form.is_valid()
        self.assertIn('cycle_terms', form.errors)

    def test_cycle_terms_same_ay_passes_ay_check(self):
        data = _qdict([
            ('cycle_terms', [str(self.fall_a.id), str(self.spring_a.id)]),
        ])
        form = FSForm(self.request, data=data)
        form.is_valid()
        self.assertNotIn('cycle_terms', form.errors)

    def test_academic_year_derived_from_cycle_terms_on_save(self):
        data = _qdict([
            ('cycle_terms', [str(self.fall_a.id), str(self.spring_a.id)]),
            ('lookback_terms', []),
        ])
        form = FSForm(self.request, data=data)
        form.is_valid()
        derived_ay = form._derive_academic_year_from_cycle_terms()
        self.assertEqual(derived_ay, self.ay_a)
