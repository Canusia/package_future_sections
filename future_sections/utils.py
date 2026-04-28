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


def build_initial_from_prev_year(teacher_course):
    """Build formset initial data from previous year ClassSections using term mapping.

    Collapses to one row per previous-year term. Maps terms using the
    ``term_mapping`` stored in settings. Unmapped terms get a blank term value.
    """
    import json
    from cis.models.section import ClassSection

    fs_config = get_fs_config()
    previous_academic_year_id = fs_config.get('previous_academic_year')
    if not previous_academic_year_id:
        return []

    try:
        term_mapping = json.loads(fs_config.get('term_mapping', '{}'))
    except (json.JSONDecodeError, TypeError):
        term_mapping = {}

    if not term_mapping:
        return []

    highschool = teacher_course.teacher_highschool.highschool
    teacher = teacher_course.teacher_highschool.teacher
    course = teacher_course.course

    prev_sections = ClassSection.objects.filter(
        term__academic_year__id=previous_academic_year_id,
        highschool=highschool,
        teacher=teacher,
        course=course,
        status='active',
    ).select_related('term').order_by('term__code')

    seen_terms = set()
    initial_data = []
    for section in prev_sections:
        prev_term_id = str(section.term_id)
        if prev_term_id in seen_terms:
            continue
        seen_terms.add(prev_term_id)

        mapped_term_id = term_mapping.get(prev_term_id, '')
        initial_data.append({
            'term': mapped_term_id or '',
            'highschool_course_name': section.highschool_course_name or '',
        })

    return initial_data


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


def build_section_info_from_formset(request, teaching_formset, future_course):
    """
    Convert a validated teaching formset into the section_info payload
    persisted on FutureCourse.section_info['sections'].

    Per section it:
      - Skips empty rows (no `term`).
      - Uploads any `form-<i>-syllabus` file to PrivateMediaStorage and stores
        the resulting URL in cleaned_data['file'].
      - Drops the raw UploadedFile (`syllabus` key) since UploadedFile is not
        JSON-serializable; cleaned_data['file'] holds the saved URL instead.

    Args:
        request: Current HttpRequest (used for request.FILES).
        teaching_formset: A bound, validated TeachingFormSet.
        future_course: FutureCourse (used in the storage path).

    Returns:
        list[dict]: cleaned_data dicts ready to assign to
        FutureCourse.section_info['sections'].
    """
    from cis.backends.storage_backend import PrivateMediaStorage
    from django.utils.text import get_valid_filename

    sections = []
    for index, teaching_form in enumerate(teaching_formset):
        cleaned = teaching_form.cleaned_data
        if not cleaned or not cleaned.get('term'):
            continue

        uploaded = request.FILES.get(f'form-{index}-syllabus')
        if uploaded:
            storage = PrivateMediaStorage()
            safe_name = get_valid_filename(uploaded.name)
            stored_path = storage.save(
                f'future_section/{future_course.id}/{safe_name}',
                uploaded,
            )
            cleaned['file'] = storage.url(stored_path)

        cleaned.pop('syllabus', None)
        sections.append(cleaned)
    return sections
