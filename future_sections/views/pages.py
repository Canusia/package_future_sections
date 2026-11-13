"""
Page views for future sections.

These views render the main future sections pages for different user roles.
"""

from django.conf import settings
from django.shortcuts import render
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.views import View

from ..models import FutureCourse
from cis.models.highschool_administrator import HSPosition
from cis.models.term import AcademicYear

from ..forms import (
    ConfirmHighSchoolAdministratorsForm,
    ConfirmClassSectionsForm
)
from ..portal_text import page_blurb, page_heading
from ..utils import get_fs_config, get_user_context


# The HS admin portal settings form saves each page's text under
# '<menu item name>_blurb', so this page's key is 'future_sections_blurb'.
# 'section_requests_blurb' is the key this page used to read; tenants that
# only ever stored that one keep seeing it until they save the new key.
INTRO_BLURB_KEYS = ('future_sections_blurb', 'section_requests_blurb')


# The menu item this page lights up. The cis menu registry names it
# 'future_sections' for both portals (#13); a cis from before the registry
# keeps the settings-driven menu, where it was 'section_requests'.
MENU_ITEM_NAMES = ('future_sections', 'section_requests')


def active_menu_item(role):
    """The name this page's item has in ``role``'s menu ('future_sections' if unsure)."""
    try:
        from cis.menu import get_role_menu
    except ImportError:
        # cis < v0.0.34 has only the settings-driven menu ('section_requests').
        return MENU_ITEM_NAMES[1]
    try:
        items = list(get_role_menu(role, visible_only=False) or ())
    except Exception:
        return MENU_ITEM_NAMES[0]
    names = set()
    while items:
        item = items.pop()
        if isinstance(item, dict):
            names.add(item.get('name'))
            items.extend(item.get('sub_menu') or ())
    return next((n for n in MENU_ITEM_NAMES if n in names), MENU_ITEM_NAMES[0])


def page_intro(role, item=None):
    """The Course Information text staff saved for ``role``, or ''.

    Always 'future_sections_blurb' first (what the settings form saves),
    then the legacy key, whatever the menu item is called.
    """
    return page_blurb(role, 'future_sections', legacy_keys=INTRO_BLURB_KEYS[1:])


def hs_admin_intro(request):
    """The HS admin Course Information intro text, or '' when none is saved."""
    return page_intro('highschool_admin', 'future_sections')


FALLBACK_BREADCRUMB = 'future_sections/partials/_breadcrumb.html'


def breadcrumb_template(portal_key):
    """The portal's own breadcrumb partial, or this package's fallback.

    Not every tenant's HS admin / instructor portal ships
    ``<portal>/partials/_breadcrumb.html`` (package_future_sections#9); an
    unguarded include of a missing one 500s the whole page.
    """
    name = f'{portal_key}/partials/_breadcrumb.html'
    try:
        get_template(name)
    except TemplateDoesNotExist:
        return FALLBACK_BREADCRUMB
    return name


class FutureSectionsPageView(View):
    """
    Unified future sections page view for both HS Admin and Instructor roles.

    Renders the main future sections page with:
    - Course requests table (loaded via AJAX)
    - School personnel tab (if configured)
    - Confirmation forms
    """

    def get(self, request):
        fs_config = get_fs_config()
        context = get_user_context(request)

        # Role-specific configuration
        if context['is_admin']:
            from cis.menu import draw_menu, HS_ADMIN_MENU
            menu_item = active_menu_item('highschool_admin')
            menu = draw_menu(HS_ADMIN_MENU, menu_item, '', 'highschool_admin')
            portal_key = 'highschool_admin'
            base_template = 'highschool_admin/base_hsadmin.html'
            url_namespace = 'future_sections_highschool_admin'
        else:
            from cis.menu import draw_menu, INSTRUCTOR_MENU
            menu_item = active_menu_item('instructor')
            menu = draw_menu(INSTRUCTOR_MENU, menu_item, '', 'instructor')
            portal_key = 'instructor'
            base_template = 'instructor/base_instructor.html'
            url_namespace = 'future_sections_instructor'

        highschools = context['highschools']

        # Initialize forms for display
        confirm_admins_form = ConfirmHighSchoolAdministratorsForm(
            highschools=highschools
        )
        confirm_sections_form = ConfirmClassSectionsForm(
            highschools=highschools,
            action='confirmed_class_sections'
        )

        # Get academic year from config
        academic_year = AcademicYear.objects.get(
            pk=fs_config.get('academic_year', AcademicYear.objects.first().id)
        )

        # Get configured roles for school personnel tab
        hs_roles = HSPosition.objects.filter(
            id__in=fs_config.get('school_admin_roles', [])
        ).order_by('name')

        window_is_open = FutureCourse.is_window_open()

        # Build URLs using the correct portal namespace
        from django.urls import reverse
        api_urls = {
            'mark_teaching': reverse(f'{url_namespace}:actions-mark-teaching'),
            'mark_not_teaching': reverse(f'{url_namespace}:actions-mark-not-teaching'),
            'remove_teaching_status': reverse(f'{url_namespace}:actions-remove-teaching-status'),
            'add_teacher': reverse(f'{url_namespace}:actions-add-teacher'),
            'admin_assign': reverse(f'{url_namespace}:admin-positions-assign'),
            'admin_positions': reverse(f'{url_namespace}:admin-positions-list'),
            'course_requests': reverse(f'{url_namespace}:course-requests-list'),
            'confirm_sections': reverse(f'{url_namespace}:actions-confirm-sections'),
            'confirm_administrators': reverse(f'{url_namespace}:actions-confirm-administrators'),
        }

        # Each portal's own saved text; instructors used to get the HS admin's (#12).
        intro = page_intro(portal_key, menu_item)

        template = 'future_sections/future_sections.html'

        return render(request, template, {
            'base_template': base_template,
            'menu': menu,
            'portal_key': portal_key,
            'breadcrumb_template': breadcrumb_template(portal_key),
            'is_admin': context['is_admin'],
            'window_is_open': window_is_open,
            'allow_teacher_create': fs_config.get('allow_new_teacher_create', '1') == '1',
            'new_teacher_create_label': fs_config.get('new_teacher_create_label', 'Change me'),
            'enter_course_details_label': (
                fs_config.get('enter_course_details_label')
                or 'Enter Course Details'),
            'not_teaching_label': (
                fs_config.get('not_teaching_label')
                or 'We are not teaching this course'),
            'window_closed_message': fs_config.get('window_closed_message'),
            'welcome_message': FutureCourse.welcome_message(highschools),
            'welcome_message_personnel': fs_config.get('welcome_message_personnel', 'Change Me'),
            'confirm_administrators_header': fs_config.get('confirm_administrators_header', 'Change Me'),
            'intro': intro,
            'academic_year': academic_year,
            'hs_roles': hs_roles,
            'highschools': highschools,
            'confirm_admins_form': confirm_admins_form,
            'confirm_sections_form': confirm_sections_form,
            # A renamed menu item wins over the page_name setting (#12).
            'page_name': page_heading(portal_key, menu_item,
                                      fs_config.get('page_name', 'Future Section Requests')),
            'tab_course_requests': fs_config.get('tab_course_requests', 'Course Requests'),
            'tab_school_personnel': fs_config.get('tab_school_personnel', 'School Personnel'),
            'api_urls': api_urls,
            # In dev, concurrent local tenants on 127.0.0.1 share cookie scope,
            # so the host's settings.py renames CSRF_COOKIE_NAME per tenant
            # (e.g. ewu_csrftoken). Expose it so future_sections.js can read
            # the right cookie. In production CSRF_COOKIE_NAME stays at
            # Django's default and the template skips the inline override.
            'debug': settings.DEBUG,
            'csrf_cookie_name': settings.CSRF_COOKIE_NAME,
        })
