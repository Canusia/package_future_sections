"""The Course Information page marks its own sidebar item active (#13).

The HS admin and instructor menu items are registered as 'future_sections';
the page used to pass the retired name 'section_requests', so nothing was
highlighted.
"""
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from ..views import pages


REGISTRY_MENU = [{'name': 'home'}, {'name': 'future_sections'}]
LEGACY_MENU = [{'name': 'home'}, {'name': 'section_requests'}]


class _Stop(Exception):
    pass


def _active_item(is_admin, menu=REGISTRY_MENU):
    """The (active item, role) the page passes to draw_menu."""
    with mock.patch.object(pages, 'get_fs_config', return_value={}), \
            mock.patch.object(pages, 'get_user_context',
                              return_value={'is_admin': is_admin, 'highschools': []}), \
            mock.patch('cis.menu.draw_menu', side_effect=_Stop) as draw, \
            mock.patch('cis.menu.get_role_menu', return_value=menu):
        try:
            pages.FutureSectionsPageView().get(RequestFactory().get('/'))
        except _Stop:
            pass
    args = draw.call_args.args
    return args[1], args[3]


class PageActiveMenuTests(SimpleTestCase):

    def test_hs_admin_page_marks_future_sections_active(self):
        self.assertEqual(_active_item(True), ('future_sections', 'highschool_admin'))

    def test_instructor_page_marks_future_sections_active(self):
        self.assertEqual(_active_item(False), ('future_sections', 'instructor'))

    def test_cis_before_the_registry_keeps_section_requests(self):
        self.assertEqual(_active_item(True, LEGACY_MENU),
                         ('section_requests', 'highschool_admin'))

    def test_item_inside_a_group_is_found(self):
        menu = [{'name': 'grp', 'sub_menu': [{'name': 'section_requests'}]}]
        self.assertEqual(_active_item(False, menu), ('section_requests', 'instructor'))

    def test_unreadable_menu_uses_future_sections(self):
        with mock.patch('cis.menu.get_role_menu', side_effect=RuntimeError):
            self.assertEqual(pages.active_menu_item('instructor'), 'future_sections')

    def test_menu_ids_match_the_registry(self):
        from ..menu import menu
        if menu is None:
            self.skipTest('cis has no menu registry')
        for role in ('highschool_admin', 'instructor'):
            ids = {item.get('name') for item in menu.items(role)}
            self.assertIn('future_sections', ids, role)
