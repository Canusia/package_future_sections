"""
URL Configuration for future_sections in highschool_admin portal.

Provides the future sections page and API endpoints for high school administrators.
"""

from django.urls import path, include
from django.contrib.auth.decorators import user_passes_test

from rest_framework import routers

from cis.utils import user_has_highschool_admin_role

from ..views import (
    FutureSectionsActionViewSet,
    CourseRequestViewSet,
    AdminPositionViewSet,
    FutureSectionsPageView,
)

app_name = 'future_sections_highschool_admin'

router = routers.DefaultRouter()
router.register('actions', FutureSectionsActionViewSet, basename='actions')
router.register('course-requests', CourseRequestViewSet, basename='course-requests')
router.register('admin-positions', AdminPositionViewSet, basename='admin-positions')

urlpatterns = [
    path('api/', include(router.urls)),
    path(
        '',
        user_passes_test(user_has_highschool_admin_role, login_url='/')(
            FutureSectionsPageView.as_view()
        ),
        name='section_requests'
    ),
]
