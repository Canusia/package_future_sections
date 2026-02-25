"""
CE Portal URL Configuration for Future Sections
"""
from django.urls import path, include
from django.contrib.auth.decorators import user_passes_test

from rest_framework import routers

from ..views.ce import (
    index, detail, settings, delete_section, future_sections_actions,
    bulk_actions, get_highschool_admins, send_pending_reminder
)
from ..views.ce_api import (
    PendingFutureClassSectionViewSet,
    FutureProjectionViewSet,
    FutureClassSectionViewSet,
    NotificationLogViewSet
)


def user_has_cis_role(user):
    """Returns True if current user has a 'ce' role."""
    if user.is_anonymous:
        return False
    roles = user.get_roles()
    return 'ce' in roles


# API router for CE portal
router = routers.DefaultRouter()
router.register('future_class_section', FutureClassSectionViewSet, basename='future_class_section')
router.register('future_projection', FutureProjectionViewSet, basename='future_projection')
router.register('pending_future_class_sections', PendingFutureClassSectionViewSet, basename='pending_future_class_sections')
router.register('notification_logs', NotificationLogViewSet, basename='notification_logs')

app_name = 'future_sections_ce'

urlpatterns = [
    path('api/', include(router.urls)),
    path(
        '',
        user_passes_test(user_has_cis_role, login_url='/')(index),
        name='future_sections'
    ),
    path(
        'ajax',
        future_sections_actions,
        name='future_sections_actions'
    ),
    path(
        '<uuid:record_id>',
        user_passes_test(user_has_cis_role, login_url='/')(detail),
        name='future_section'
    ),
    path(
        'settings/',
        user_passes_test(user_has_cis_role, login_url='/')(settings),
        name='future_section_settings'
    ),
    path(
        'delete/',
        user_passes_test(user_has_cis_role, login_url='/')(delete_section),
        name='delete_future_section'
    ),
    path(
        'bulk_actions',
        user_passes_test(user_has_cis_role, login_url='/')(bulk_actions),
        name='bulk_actions'
    ),
    path(
        'get_highschool_admins',
        user_passes_test(user_has_cis_role, login_url='/')(get_highschool_admins),
        name='get_highschool_admins'
    ),
    path(
        'send_pending_reminder',
        user_passes_test(user_has_cis_role, login_url='/')(send_pending_reminder),
        name='send_pending_reminder'
    ),
]
