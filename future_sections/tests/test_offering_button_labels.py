"""The two offering-action button labels are tenant-configurable.

The buttons ("Enter Course Details" / "We are not teaching this course")
are built in JavaScript, so the labels have to travel from settings ->
view context -> template -> JS rather than being rendered server-side.
These tests pin each link in that chain.
"""

import os
import re

from django.test import SimpleTestCase

from future_sections.future_sections.settings.future_sections import (
    future_sections as FSForm,
)


_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HS_TEMPLATE = os.path.join(
    _PKG, 'templates', 'future_sections', 'future_sections.html')
CE_TEMPLATE = os.path.join(
    _PKG, 'templates', 'future_sections', 'ce', 'index.html')
HS_JS = os.path.join(
    _PKG, 'staticfiles', 'future_sections', 'js', 'future_sections.js')
PAGES_VIEW = os.path.join(_PKG, 'views', 'pages.py')
CE_VIEW = os.path.join(_PKG, 'views', 'ce.py')

DEFAULT_ENTER = 'Enter Course Details'
DEFAULT_NOT_TEACHING = 'We are not teaching this course'


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


class OfferingButtonLabelSettingTests(SimpleTestCase):
    def test_both_settings_are_declared(self):
        for name in ('enter_course_details_label', 'not_teaching_label'):
            self.assertIn(name, FSForm.base_fields, name)

    def test_settings_are_optional(self):
        # Blank falls back to the default label rather than blocking a save.
        for name in ('enter_course_details_label', 'not_teaching_label'):
            self.assertFalse(FSForm.base_fields[name].required, name)

    def test_settings_carry_the_current_wording_as_initial(self):
        self.assertEqual(
            FSForm.base_fields['enter_course_details_label'].initial,
            DEFAULT_ENTER)
        self.assertEqual(
            FSForm.base_fields['not_teaching_label'].initial,
            DEFAULT_NOT_TEACHING)


class HSAdminWiringTests(SimpleTestCase):
    def test_view_supplies_both_labels_with_defaults(self):
        source = _read(PAGES_VIEW)
        self.assertIn("fs_config.get('enter_course_details_label'", source)
        self.assertIn("fs_config.get('not_teaching_label'", source)
        self.assertIn(DEFAULT_ENTER, source)
        self.assertIn(DEFAULT_NOT_TEACHING, source)

    def test_template_exposes_both_labels_to_js(self):
        source = _read(HS_TEMPLATE)
        self.assertIn('data-enter-details-label=', source)
        self.assertIn('data-not-teaching-label=', source)

    def test_js_reads_the_labels_from_config(self):
        source = _read(HS_JS)
        self.assertIn("config.data('enter-details-label')", source)
        self.assertIn("config.data('not-teaching-label')", source)

    def test_js_no_longer_hardcodes_the_labels_in_the_buttons(self):
        source = _read(HS_JS)
        # The wording may survive only as a fallback default, never as the
        # button text itself.
        self.assertNotIn("'Enter Course Details</button> '", source)
        self.assertNotIn("'We are not teaching this course</button>'", source)


class CEPortalWiringTests(SimpleTestCase):
    """The CE index renders the same two buttons; it must honour the same
    labels, or the two portals drift apart."""

    def test_view_supplies_both_labels_with_defaults(self):
        source = _read(CE_VIEW)
        self.assertIn("enter_course_details_label", source)
        self.assertIn("not_teaching_label", source)

    def test_template_uses_the_context_labels_not_literals(self):
        source = _read(CE_TEMPLATE)
        self.assertIn('{{ enter_course_details_label', source)
        self.assertIn('{{ not_teaching_label', source)
        # The old hardcoded button text must be gone from the row renderer.
        self.assertNotIn('>Enter Course Details</button>', source)
        self.assertNotIn('>Not teaching this course</button>', source)
