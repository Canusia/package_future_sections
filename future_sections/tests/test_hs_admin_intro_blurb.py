"""The HS admin Course Information page shows the blurb the portal settings
form saves ('future_sections_blurb'), falling back to the legacy
'section_requests_blurb' (package-highschool_admin#24)."""
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from ..views import pages


def _intro(stored):
    portal = mock.Mock()
    portal.return_value.from_db.return_value = stored
    with mock.patch('cis.settings.highschool_admin_portal.highschool_admin_portal', portal):
        return pages.hs_admin_intro(RequestFactory().get('/'))


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
