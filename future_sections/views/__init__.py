# Future sections views
from .api import FutureSectionsActionViewSet, CourseRequestViewSet, AdminPositionViewSet
from .pages import FutureSectionsPageView
from .instructor import future_sections_view as instructor_future_sections_view
from .hs_admin import future_sections_view as hs_admin_future_sections_view

# CE portal views
from .ce import (
    index as ce_index,
    detail as ce_detail,
    settings as ce_settings,
    delete_section as ce_delete_section,
    future_sections_actions as ce_future_sections_actions,
    mark_as_teaching as ce_mark_as_teaching,
    mark_as_not_teaching as ce_mark_as_not_teaching,
    remove_marked_as_not_teaching as ce_remove_marked_as_not_teaching,
    send_survey_to_instructors as ce_send_survey_to_instructors,
)
from .ce_api import (
    PendingFutureClassSectionViewSet,
    FutureProjectionViewSet,
    FutureClassSectionViewSet,
)

__all__ = [
    'FutureSectionsActionViewSet',
    'CourseRequestViewSet',
    'AdminPositionViewSet',
    'FutureSectionsPageView',
    'instructor_future_sections_view',
    'hs_admin_future_sections_view',
    # CE views
    'ce_index',
    'ce_detail',
    'ce_settings',
    'ce_delete_section',
    'ce_future_sections_actions',
    'ce_mark_as_teaching',
    'ce_mark_as_not_teaching',
    'ce_remove_marked_as_not_teaching',
    'ce_send_survey_to_instructors',
    # CE API ViewSets
    'PendingFutureClassSectionViewSet',
    'FutureProjectionViewSet',
    'FutureClassSectionViewSet',
]
