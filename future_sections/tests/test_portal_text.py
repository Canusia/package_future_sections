"""Headings follow renamed menu items; each portal shows its own page text (#12)."""
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from .. import portal_text
from ..review import views as review_views
from ..views import pages

MENU = 'cis.menu.get_role_menu'


def _no_cis(portal_text_fn=None):
    """Behave like a cis without cis.portal_text.page_heading/page_blurb."""
    return mock.patch.object(
        portal_text, '_cis_helper',
        side_effect=lambda name: portal_text_fn if name == 'portal_text' else None)


class FallbackHeadingTests(SimpleTestCase):

    def test_renamed_label_wins(self):
        with _no_cis(), mock.patch(MENU, return_value=[
                {'name': 'future_sections', 'label': 'DC Course Info'}]):
            self.assertEqual(portal_text.page_heading('highschool_admin', 'future_sections', 'D'),
                             'DC Course Info')

    def test_stock_missing_or_unreadable_keeps_default(self):
        for menu in ([{'name': 'future_sections', 'label': 'Future Sections'}],
                     [{'name': 'section_requests', 'label': 'Course Projections'}],
                     [{'name': 'home', 'label': 'Home'}]):
            with _no_cis(), mock.patch(MENU, return_value=menu):
                self.assertEqual(portal_text.page_heading('highschool_admin', 'future_sections', 'D'), 'D')
        with _no_cis(), mock.patch(MENU, side_effect=RuntimeError):
            self.assertEqual(portal_text.page_heading('instructor', 'future_sections', 'D'), 'D')


class FallbackBlurbTests(SimpleTestCase):

    def test_instructor_and_faculty_text_follow_the_owning_package(self):
        owned = lambda name: {'future_sections_blurb': name, 'section_requests_blurb': name}
        with _no_cis(owned):
            self.assertEqual(portal_text.page_blurb('instructor', 'future_sections'),
                             'instructor_portal')
            self.assertEqual(portal_text.page_blurb('faculty', 'section_requests'),
                             'faculty_portal')

    def test_placeholders_unknown_roles_and_errors(self):
        with _no_cis(), mock.patch.object(portal_text, '_stored_text',
                                          return_value={'x_blurb': 'Change me'}):
            self.assertEqual(portal_text.page_blurb('highschool_admin', 'x', default='D'), 'D')
        self.assertEqual(portal_text.page_blurb('ce', 'x', default='D'), 'D')
        with _no_cis(), mock.patch.object(portal_text, '_stored_text', side_effect=RuntimeError):
            self.assertEqual(portal_text.page_blurb('student', 'x'), '')


class CisHelperTests(SimpleTestCase):
    """With cis.portal_text.page_heading/page_blurb, those are used."""

    def test_delegates(self):
        heading = mock.Mock(return_value='H')
        blurb = mock.Mock(return_value='B')
        helpers = {'page_heading': heading, 'page_blurb': blurb}
        with mock.patch.object(portal_text, '_cis_helper', side_effect=helpers.get):
            self.assertEqual(portal_text.page_heading('ce', 'future_sections', 'D'), 'H')
            self.assertEqual(portal_text.page_blurb('faculty', 'section_requests',
                                                    legacy_keys=('k',)), 'B')
        heading.assert_called_once_with('ce', 'future_sections', 'D')
        blurb.assert_called_once_with('faculty', 'section_requests', legacy_keys=('k',), default='')


class _Stop(Exception):
    pass


class CourseInformationPageTests(SimpleTestCase):
    """The page passes its own role's heading and text."""

    def _context(self, is_admin):
        captured = {}

        def fake_render(request, template, context):
            captured.update(context)
            raise _Stop

        with mock.patch.object(pages, 'get_fs_config', return_value={'page_name': 'Setting Name'}), \
                mock.patch.object(pages, 'get_user_context',
                                  return_value={'is_admin': is_admin, 'highschools': []}), \
                mock.patch('cis.menu.draw_menu', return_value=''), \
                mock.patch.object(pages, 'active_menu_item', return_value='future_sections'), \
                mock.patch.object(pages, 'page_heading', side_effect=lambda r, n, d: f'{r}:{n}:{d}'), \
                mock.patch.object(pages, 'page_intro', side_effect=lambda r, n: f'intro {r}'), \
                mock.patch.object(pages, 'render', side_effect=fake_render), \
                mock.patch.object(pages, 'breadcrumb_template', return_value=''), \
                mock.patch.object(pages, 'FutureCourse'), \
                mock.patch.object(pages, 'AcademicYear'), \
                mock.patch.object(pages, 'HSPosition'), \
                mock.patch.object(pages, 'ConfirmHighSchoolAdministratorsForm'), \
                mock.patch.object(pages, 'ConfirmClassSectionsForm'):
            try:
                pages.FutureSectionsPageView().get(RequestFactory().get('/'))
            except _Stop:
                pass
        return captured

    def test_hs_admin(self):
        ctx = self._context(True)
        self.assertEqual(ctx['page_name'], 'highschool_admin:future_sections:Setting Name')
        self.assertEqual(ctx['intro'], 'intro highschool_admin')

    def test_instructor_gets_its_own_text(self):
        ctx = self._context(False)
        self.assertEqual(ctx['page_name'], 'instructor:future_sections:Setting Name')
        self.assertEqual(ctx['intro'], 'intro instructor')


class ReviewListHeadingTests(SimpleTestCase):

    def test_faculty_list_follows_its_menu_item(self):
        with mock.patch.object(review_views, 'page_heading', return_value='Course Reviews') as h, \
                mock.patch.object(review_views, 'page_blurb', return_value='Text') as b:
            self.assertEqual(review_views._list_heading('faculty'), 'Course Reviews')
            self.assertEqual(review_views._list_intro('faculty'), 'Text')
        h.assert_called_once_with('faculty', 'section_requests', 'Section Requests')
        b.assert_called_once_with('faculty', 'section_requests')

    def test_ce_list_keeps_its_heading(self):
        self.assertEqual(review_views._list_heading('ce'), 'Section Requests')
        self.assertEqual(review_views._list_intro('ce'), '')
