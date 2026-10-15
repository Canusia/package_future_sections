"""Guards on the AY-scoped term checkboxes in staticfiles/.../settings.js.

There is no JS test runner in this package, so these scan the shipped file for
the two regressions EWU hit (2026-10): changing an academic year left the old
year's checkboxes on the page (crispy renders div.custom-control, not <ul>), so
their duplicate ids made the boxes impossible to uncheck and the stale ticks
tripped the multi-year warning; and the warning guessed a term's year from the
first 4-digit number in its label, so one AY's Fall 2026 and Spring 2027 terms
read as two years. The behaviour itself was checked in the browser.
"""
import os

from django.test import SimpleTestCase

JS = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'staticfiles', 'future_sections', 'js', 'settings.js')


class SettingsTermListJsTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(JS, encoding='utf-8') as f:
            cls.js = f.read()
        start = cls.js.index('function rebuildTermCheckboxes')
        cls.rebuild = cls.js[start:cls.js.index('var _ayScopedTermsInitialized')]

    def test_rebuild_removes_crispy_custom_control_choices(self):
        self.assertIn('.custom-control', self.rebuild)
        self.assertIn('.remove()', self.rebuild)

    def test_rebuilt_ids_do_not_reuse_the_server_rendered_ids(self):
        self.assertNotIn("'id_' + termName + '_' + i", self.rebuild)

    def test_rebuilt_inputs_carry_their_academic_year(self):
        self.assertIn('data-academic-year', self.rebuild)

    def test_multi_year_hint_does_not_guess_from_four_digits(self):
        self.assertNotIn('\\d{4}', self.js)
