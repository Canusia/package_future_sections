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


class TermFieldOrderTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/?report_id=1')

    def test_ay_selectors_precede_their_term_lists(self):
        keys = list(FSForm(self.request).fields.keys())
        self.assertLess(keys.index('academic_year'), keys.index('cycle_terms'))
        self.assertLess(
            keys.index('previous_academic_year'), keys.index('lookback_terms'))


class TermQuerysetScopingTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/?report_id=1')
        self.ay_req = AcademicYear.objects.create(name='2026-2027')
        self.ay_prev = AcademicYear.objects.create(name='2025-2026')
        self.req_fall = Term.objects.create(
            code='FA26', label='Fall 2026', academic_year=self.ay_req)
        self.req_spring = Term.objects.create(
            code='SP27', label='Spring 2027', academic_year=self.ay_req)
        self.prev_fall = Term.objects.create(
            code='FA25', label='Fall 2025', academic_year=self.ay_prev)

    def test_unbound_cycle_terms_scoped_to_requesting_ay(self):
        form = FSForm(self.request, initial={
            'academic_year': str(self.ay_req.id),
            'previous_academic_year': str(self.ay_prev.id),
        })
        cycle_ids = {str(t.id) for t in form.fields['cycle_terms'].queryset}
        self.assertEqual(
            cycle_ids, {str(self.req_fall.id), str(self.req_spring.id)})

    def test_unbound_lookback_terms_scoped_to_previous_ay(self):
        form = FSForm(self.request, initial={
            'academic_year': str(self.ay_req.id),
            'previous_academic_year': str(self.ay_prev.id),
        })
        lookback_ids = {str(t.id) for t in form.fields['lookback_terms'].queryset}
        self.assertEqual(lookback_ids, {str(self.prev_fall.id)})

    def test_unbound_without_initial_is_empty(self):
        form = FSForm(self.request)
        self.assertEqual(form.fields['cycle_terms'].queryset.count(), 0)
        self.assertEqual(form.fields['lookback_terms'].queryset.count(), 0)

    def test_render_shows_only_requesting_ay_terms(self):
        form = FSForm(self.request, initial={
            'academic_year': str(self.ay_req.id),
            'previous_academic_year': str(self.ay_prev.id),
        })
        html = str(form['cycle_terms'])
        self.assertIn('Fall 2026', html)
        self.assertIn('Spring 2027', html)
        self.assertNotIn('Fall 2025', html)

    def test_bound_form_keeps_full_queryset_for_validation(self):
        data = _qdict([('cycle_terms', [str(self.req_fall.id)])])
        form = FSForm(self.request, data=data)
        self.assertEqual(
            form.fields['cycle_terms'].queryset.count(), Term.objects.count())
        self.assertEqual(
            form.fields['lookback_terms'].queryset.count(), Term.objects.count())

    def test_bound_valid_cycle_terms_not_rejected(self):
        data = _qdict([
            ('cycle_terms', [str(self.req_fall.id), str(self.req_spring.id)]),
        ])
        form = FSForm(self.request, data=data)
        form.is_valid()
        self.assertNotIn('cycle_terms', form.errors)
