"""The Course Information page shows the text each portal's settings form
saves ('future_sections_blurb'), falling back to the legacy
'section_requests_blurb' (package-highschool_admin#24, #12)."""
from unittest import mock

from django.test import SimpleTestCase

from .. import portal_text
from ..views import pages


def _intro(stored, role='highschool_admin', item='future_sections'):
    # Read the fallback path; the cis helper path is covered in test_portal_text.
    with mock.patch.object(portal_text, '_cis_helper', return_value=None), \
            mock.patch.object(portal_text, '_stored_text', return_value=stored):
        return pages.page_intro(role, item)


class HsAdminIntroBlurbTests(SimpleTestCase):

    def test_reads_the_key_the_settings_form_saves(self):
        self.assertEqual(_intro({'future_sections_blurb': 'New',
                                 'section_requests_blurb': 'Old'}), 'New')

    def test_falls_back_to_the_legacy_key(self):
        self.assertEqual(_intro({'section_requests_blurb': 'Old'}), 'Old')
        self.assertEqual(_intro({'future_sections_blurb': '',
                                 'section_requests_blurb': 'Old'}), 'Old')

    def test_nothing_saved_is_blank(self):
        self.assertEqual(_intro({}), '')
        self.assertEqual(_intro(None), '')

    def test_hs_admin_intro_wrapper(self):
        with mock.patch.object(pages, 'page_intro', return_value='X') as m:
            self.assertEqual(pages.hs_admin_intro(None), 'X')
        m.assert_called_once_with('highschool_admin', 'future_sections')
