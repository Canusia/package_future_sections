"""Faculty-portal URLs for section-request review."""
from django.urls import path, include
from django.contrib.auth.decorators import user_passes_test
from rest_framework import routers

from cis.utils import user_has_faculty_role

from ..review import views as rv
from ..review.api import SectionRequestViewSet


app_name = 'future_sections_faculty'

faculty_only = lambda v: user_passes_test(user_has_faculty_role, login_url='/')(v)


def _list(request):
    return rv.section_request_list(request, portal='faculty')


def _detail(request, future_course_id):
    return rv.section_request_detail(request, future_course_id, portal='faculty')


# Subclass the generic viewset to pin the detail-URL name for serialization.
class FacultySectionRequestViewSet(SectionRequestViewSet):
    detail_url_name = 'future_sections_faculty:section_request_detail'


router = routers.DefaultRouter()
router.register('section_request', FacultySectionRequestViewSet, basename='section_request')

urlpatterns = [
    path('section_requests/', faculty_only(_list), name='section_request_list'),
    path('section_requests/<uuid:future_course_id>/', faculty_only(_detail),
         name='section_request_detail'),
    path('section_request_api/', include(router.urls)),
]
