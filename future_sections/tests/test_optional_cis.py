"""future_sections installs and runs on a tenant with an in-repo cis
(package_future_sections#9): no hard myce_cis requirement, no campus
narrowing when cis has no highschool_scope, and a breadcrumb that does not
depend on the portal shipping its own partial."""
import configparser
import os
import uuid
from unittest import mock

from django.template import TemplateDoesNotExist
from django.template.loader import get_template, render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import NoReverseMatch

from cis.models.highschool import HighSchool

from . import PKG
from .. import forms
from ..views import pages

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


class MetadataTests(SimpleTestCase):
    """myce_cis is an extra, never an install requirement."""

    def _read(self, name):
        path = os.path.join(REPO_ROOT, name)
        if not os.path.exists(path):  # installed wheel: no repo metadata
            self.skipTest(f'{name} not shipped')
        with open(path) as fh:
            return fh.read()

    def test_setup_cfg_install_requires_has_no_myce_cis(self):
        cfg = configparser.ConfigParser()
        cfg.read_string(self._read('setup.cfg'))
        self.assertNotIn('myce_cis', cfg['options']['install_requires'])
        self.assertIn('myce_cis', cfg['options.extras_require']['campus'])

    def test_setup_py_install_requires_has_no_myce_cis(self):
        src = self._read('setup.py')
        start = src.index('install_requires=[')
        block = src[start:src.index(']', start)]
        self.assertNotIn('myce_cis', block)
        self.assertIn("'campus': ['myce_cis", src)


class CampusNarrowWithoutScopeTests(TestCase):
    def test_no_highschool_scope_leaves_queryset_alone(self):
        sfx = uuid.uuid4().hex[:8]
        hs = HighSchool.objects.create(name=f'Unlinked {sfx}', code=sfx)
        qs = HighSchool.objects.filter(pk=hs.pk)
        with mock.patch(f'{PKG}.forms.picker_queryset', None):
            self.assertEqual(list(forms._campus_narrow(qs)), [hs])


class BreadcrumbFallbackTests(SimpleTestCase):
    def test_missing_portal_partial_uses_package_fallback(self):
        def fake_get_template(name, *a, **kw):
            if name.endswith('/partials/_breadcrumb.html') \
                    and not name.startswith('future_sections/'):
                raise TemplateDoesNotExist(name)
            return get_template(name, *a, **kw)

        with mock.patch(f'{PKG}.views.pages.get_template', fake_get_template):
            self.assertEqual(pages.breadcrumb_template('instructor'),
                             pages.FALLBACK_BREADCRUMB)
            self.assertEqual(pages.breadcrumb_template('highschool_admin'),
                             pages.FALLBACK_BREADCRUMB)

    def test_existing_portal_partial_is_used(self):
        with mock.patch(f'{PKG}.views.pages.get_template'):
            self.assertEqual(pages.breadcrumb_template('instructor'),
                             'instructor/partials/_breadcrumb.html')

    def test_fallback_renders_page_name_without_portal_urls(self):
        # URLNode imports reverse at render time.
        with mock.patch('django.urls.reverse', side_effect=NoReverseMatch):
            html = render_to_string(pages.FALLBACK_BREADCRUMB, {
                'portal_key': 'instructor', 'page_name': 'Course Information'})
        self.assertIn('Course Information', html)
        self.assertNotIn('Home', html)

    def test_page_template_has_no_hardcoded_portal_partial(self):
        src = get_template('future_sections/future_sections.html').template.source
        self.assertNotIn('highschool_admin/partials/_breadcrumb.html', src)
        self.assertNotIn('instructor/partials/_breadcrumb.html', src)
