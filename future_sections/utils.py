"""
Utility functions for the future_sections app.

Shared by both instructor and highschool_admin views.
"""

import datetime

from django.shortcuts import get_object_or_404

from rest_framework.exceptions import PermissionDenied

from .models import FutureCourse, FutureProjection
from cis.models.highschool import HighSchool
from cis.models.highschool_administrator import HSAdministrator
from cis.models.teacher import Teacher, TeacherCourseCertificate
from cis.models.term import AcademicYear
from cis.utils import user_has_highschool_admin_role, user_has_instructor_role


def get_fs_config():
    """
    Get future sections configuration from database.

    Returns:
        dict: Configuration settings for future sections
    """
    from .settings.future_sections import future_sections as fs_settings
    return fs_settings.from_db()


def get_user_context(request):
    """
    Get the user's role context for future sections operations.

    Returns a dict with:
    - highschools: QuerySet of accessible highschools
    - teacher: Teacher instance (if instructor) or None
    - is_admin: True if user is a highschool admin

    Args:
        request: HTTP request with authenticated user

    Returns:
        dict with user context information
    """
    if user_has_highschool_admin_role(request.user):
        hs_admin = HSAdministrator.objects.get(user=request.user)
        return {
            'highschools': hs_admin.get_highschools(),
            'teacher': None,
            'is_admin': True
        }
    elif user_has_instructor_role(request.user):
        teacher = Teacher.objects.get(user=request.user)
        teacher_hs = teacher.get_highschools(teacher)
        return {
            'highschools': HighSchool.objects.filter(
                id__in=teacher_hs.values_list('highschool__id')
            ),
            'teacher': teacher,
            'is_admin': False
        }
    else:
        raise PermissionDenied("User is not an instructor or highschool administrator")


def validate_certificate_access(request, teacher_course):
    """
    Verify user can access this TeacherCourseCertificate.

    For HS Admins: Certificate must be for a highschool they manage
    For Instructors: Certificate must belong to them

    Args:
        request: HTTP request with authenticated user
        teacher_course: TeacherCourseCertificate instance

    Raises:
        PermissionDenied: If user cannot access the certificate
    """
    context = get_user_context(request)

    if context['is_admin']:
        if teacher_course.teacher_highschool.highschool not in context['highschools']:
            raise PermissionDenied("No access to this highschool")
    else:
        if teacher_course.teacher_highschool.teacher != context['teacher']:
            raise PermissionDenied("You do not have permission to access this course")


def get_or_create_future_projection(highschool_id, user):
    """
    Get or create a FutureProjection for a highschool and academic year.

    Args:
        highschool_id: UUID of the highschool
        user: The user creating the projection

    Returns:
        FutureProjection instance
    """
    fs_config = get_fs_config()
    academic_year_id = fs_config.get('academic_year')

    projection = FutureProjection.objects.filter(
        highschool__id=highschool_id,
        academic_year__id=academic_year_id
    ).first()

    if not projection:
        projection = FutureProjection.objects.create(
            highschool=HighSchool.objects.get(pk=highschool_id),
            academic_year=AcademicYear.objects.get(pk=academic_year_id),
            created_by=user,
            meta={
                'confirmed_administrators': 'No',
                'confirmed_class_sections': 'No',
                'history': []
            }
        )

    return projection


def add_history_entry(obj, user, action):
    """
    Add a history entry to an object's meta field.

    Args:
        obj: Object with a meta JSONField (FutureCourse or FutureProjection)
        user: User performing the action
        action: Description of the action
    """
    if not obj.meta:
        obj.meta = {'history': []}

    if 'history' not in obj.meta:
        obj.meta['history'] = []

    obj.meta['history'].append({
        'user': str(user),
        'action': action,
        'on': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


def get_user_highschools(request):
    """
    Get the highschools accessible to the user.

    Args:
        request: HTTP request with authenticated user

    Returns:
        QuerySet of HighSchool instances
    """
    context = get_user_context(request)
    return context['highschools']


def get_course_certificates_for_user(request):
    """
    Get TeacherCourseCertificate records accessible to the user.

    For HS Admins: All certificates for their highschools
    For Instructors: Only their own certificates

    Args:
        request: HTTP request with authenticated user

    Returns:
        QuerySet of TeacherCourseCertificate instances
    """
    fs_config = get_fs_config()
    context = get_user_context(request)

    base_filter = {
        'course__status__in': fs_config.get('course_status', []),
        'status__in': fs_config.get('teacher_course_status', [])
    }

    if context['is_admin']:
        return TeacherCourseCertificate.objects.filter(
            teacher_highschool__highschool__in=context['highschools'],
            **base_filter
        )
    else:
        return TeacherCourseCertificate.objects.filter(
            teacher_highschool__teacher=context['teacher'],
            **base_filter
        )
