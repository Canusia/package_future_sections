"""
Page views for future sections.

These views render the main future sections pages for different user roles.
"""

from django.shortcuts import render
from django.views import View

from ..models import FutureCourse
from cis.models.highschool_administrator import HSPosition
from cis.models.term import AcademicYear

from ..forms import (
    ConfirmHighSchoolAdministratorsForm,
    ConfirmClassSectionsForm
)
from ..utils import get_fs_config, get_user_context


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
            menu = draw_menu(HS_ADMIN_MENU, 'section_requests', '', 'highschool_admin')
            portal_key = 'highschool_admin'
            base_template = 'highschool_admin/base_hsadmin.html'
        else:
            from cis.menu import draw_menu, INSTRUCTOR_MENU
            menu = draw_menu(INSTRUCTOR_MENU, 'section_requests', '', 'instructor')
            portal_key = 'instructor'
            base_template = 'instructor/base_instructor.html'

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

        # Get portal-specific intro text
        try:
            from cis.settings.highschool_admin_portal import highschool_admin_portal as portal_lang
            intro = portal_lang(request).from_db().get('section_requests_blurb', '')
        except Exception:
            intro = ''

        template = 'future_sections/future_sections.html'

        return render(request, template, {
            'base_template': base_template,
            'menu': menu,
            'portal_key': portal_key,
            'is_admin': context['is_admin'],
            'window_is_open': window_is_open,
            'allow_teacher_create': fs_config.get('allow_new_teacher_create', '1') == '1',
            'new_teacher_create_label': fs_config.get('new_teacher_create_label', 'Change me'),
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
            'page_name': fs_config.get('page_name', 'Future Section Requests'),
            'tab_course_requests': fs_config.get('tab_course_requests', 'Course Requests'),
            'tab_school_personnel': fs_config.get('tab_school_personnel', 'School Personnel'),
        })
