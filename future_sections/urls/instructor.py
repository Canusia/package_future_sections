"""
URL Configuration for future_sections in instructor portal.

Provides the future sections page and API endpoints for instructors.
"""

from django.urls import path, include
from django.contrib.auth.decorators import user_passes_test

from rest_framework import routers

from cis.utils import user_has_instructor_role

from ..views import (
    FutureSectionsActionViewSet,
    CourseRequestViewSet,
    AdminPositionViewSet,
    FutureSectionsPageView,
)

app_name = 'future_sections_instructor'

router = routers.DefaultRouter()
router.register('actions', FutureSectionsActionViewSet, basename='actions')
router.register('course-requests', CourseRequestViewSet, basename='course-requests')
router.register('admin-positions', AdminPositionViewSet, basename='admin-positions')

urlpatterns = [
    path('api/', include(router.urls)),
    path(
        '',
        user_passes_test(user_has_instructor_role, login_url='/')(
            FutureSectionsPageView.as_view()
        ),
        name='section_requests'
    ),
]
