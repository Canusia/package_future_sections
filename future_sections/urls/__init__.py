"""
URL Configuration for future_sections app.

These URLs can be included by portal apps (instructor, highschool_admin)
to provide future sections API functionality.
"""

from django.urls import path, include
from rest_framework import routers

from ..views import (
    FutureSectionsActionViewSet,
    CourseRequestViewSet,
    AdminPositionViewSet,
    FutureSectionsPageView,
)

app_name = 'future_sections'

router = routers.DefaultRouter()
router.register('actions', FutureSectionsActionViewSet, basename='actions')
router.register('course-requests', CourseRequestViewSet, basename='course-requests')
router.register('admin-positions', AdminPositionViewSet, basename='admin-positions')

urlpatterns = [
    path('api/', include(router.urls)),
    path('', FutureSectionsPageView.as_view(), name='index'),
]
