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
