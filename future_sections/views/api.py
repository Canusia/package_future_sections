"""
Shared API ViewSets for future sections operations.

These ViewSets provide role-aware access control for both
highschool administrators and instructors.
"""

import json
import datetime
import logging

from django.conf import settings as django_settings
from django.db import transaction
from django.forms.formsets import formset_factory
from django.shortcuts import render, get_object_or_404
from django.template import Context, Template
from django.template.loader import get_template
from django.utils.safestring import mark_safe

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from mailer import send_html_mail

from cis.models.highschool import HighSchool
from cis.models.highschool_administrator import HSAdministrator, HSAdministratorPosition
from cis.models.teacher import Teacher, TeacherCourseCertificate
from ..models import FutureCourse, FutureProjection
from cis.models.term import AcademicYear

from ..forms import (
    TeacherCourseBaseLinkFormSet,
    TeacherCourseSectionForm,
    TeacherCourseTeachingForm,
    AddNewTeacherForm,
    HSAdministratorPositionForm,
    ConfirmHighSchoolAdministratorsForm,
    ConfirmClassSectionsForm,
)
from ..permissions import IsHSAdminOrInstructor
from ..utils import (
    get_fs_config,
    get_user_context,
    validate_certificate_access,
    get_or_create_future_projection,
    add_history_entry,
    get_user_highschools,
    get_course_certificates_for_user,
)


class FutureSectionsActionViewSet(viewsets.ViewSet):
    """
    API ViewSet for future sections actions.

    Provides role-aware endpoints for:
    - Marking courses as teaching/not teaching
    - Removing teaching status
    - Adding new teachers (HS Admin only)

    Access is controlled by IsHSAdminOrInstructor permission,
    with additional certificate-level validation.
    """
    permission_classes = [IsHSAdminOrInstructor]

    @action(detail=False, methods=['get', 'post'], url_path='mark-teaching')
    def mark_teaching(self, request):
        """
        Mark a course as teaching with section details.

        GET: Returns the teaching form for a course
        POST: Saves the teaching information
        """
        # Handle both GET (form params) and POST (data params)
        if request.method == 'GET':
            course_certificate_id = request.GET.get('course_certificate_id')
            academic_year_id = request.GET.get('academic_year_id')
        else:
            course_certificate_id = (
                request.data.get('course_certificate_id') or
                request.data.get('teacher_course_certificate_id') or
                request.POST.get('teacher_course_certificate_id')
            )
            academic_year_id = (
                request.data.get('academic_year_id') or
                request.POST.get('academic_year_id')
            )

        if not course_certificate_id or not academic_year_id:
            return Response({
                'status': 'error',
                'message': 'course_certificate_id and academic_year_id are required'
            }, status=400)

        teacher_course = get_object_or_404(
            TeacherCourseCertificate,
            certificate_id=course_certificate_id
        )
        academic_year = get_object_or_404(AcademicYear, pk=academic_year_id)

        # Verify access based on user role
        validate_certificate_access(request, teacher_course)

        TeachingFormSet = formset_factory(
            TeacherCourseSectionForm,
            formset=TeacherCourseBaseLinkFormSet,
            extra=1
        )

        future_course = FutureCourse.get_or_add(teacher_course, academic_year, submitter=request.user)

        if future_course.section_info == {}:
            future_course.section_info = {'teaching': 'yes', 'sections': []}
            future_course.save()

        initial_data = future_course.section_info.get('sections', []) if future_course.section_info else []

        if request.method == 'POST':
            teacher_course_teaching_form = TeacherCourseTeachingForm(request.POST)
            teaching_formset = TeachingFormSet(request.POST)

            # Get or create FutureProjection
            highschool_id = teacher_course.teacher_highschool.highschool.id
            fp = get_or_create_future_projection(highschool_id, request.user)

            if teacher_course_teaching_form.is_valid() and teaching_formset.is_valid():
                section_info = []

                for index, teaching_form in enumerate(teaching_formset):
                    if teaching_form.cleaned_data and teaching_form.cleaned_data.get('term'):
                        # Handle file upload
                        uploaded_file = request.FILES.get(f'form-{index}-syllabus')
                        if uploaded_file:
                            from cis.backends.storage_backend import PrivateMediaStorage
                            from django.utils.text import get_valid_filename

                            media_storage = PrivateMediaStorage()
                            safe_filename = get_valid_filename(uploaded_file.name)
                            path = f"future_section/{future_course.id}/{safe_filename}"
                            path = media_storage.save(path, uploaded_file)
                            teaching_form.cleaned_data['file'] = media_storage.url(path)

                        section_info.append(teaching_form.cleaned_data)

                # Update future course
                future_course.section_info = {'teaching': 'yes', 'sections': section_info}
                if not future_course.meta:
                    future_course.meta = {'fp': str(fp.id), 'history': []}
                else:
                    future_course.meta['fp'] = str(fp.id)

                add_history_entry(
                    future_course, request.user,
                    f'Marked as teaching - {future_course} {len(section_info)} section(s)'
                )
                future_course.save()

                # Update projection history
                add_history_entry(fp, request.user, f'Marked as teaching - {future_course}')
                fp.save()

                return Response({
                    'status': 'Success',
                    'message': 'Successfully saved course information',
                    'action': 'reload_table'
                })
            else:
                # Build error response
                errors = {}
                for index, err in enumerate(teaching_formset.errors):
                    for field, error_message in err.items():
                        errors[f"form-{index}-{field}"] = [{'message': error_message}]

                return Response({
                    'message': 'Please correct the errors and try again.',
                    'details': mark_safe(str(teaching_formset.non_form_errors())),
                    'errors': json.dumps(errors),
                    'status': 'error'
                }, status=400)
        else:
            # GET request - render form
            teacher_course_teaching_form = TeacherCourseTeachingForm(
                initial={
                    'teacher_course_certificate_id': teacher_course.certificate_id,
                    'academic_year_id': academic_year.id,
                }
            )
            teaching_formset = TeachingFormSet(initial=initial_data)

        fs_config = get_fs_config()

        # Get teaching form configuration
        try:
            form_config = json.loads(fs_config.get('teaching_form_config', '{}'))
        except Exception:
            form_config = {}

        # Set defaults if not configured
        if 'fields' not in form_config:
            form_config['fields'] = ['term', 'estimated_enrollment']
        if 'show_syllabus' not in form_config:
            form_config['show_syllabus'] = False

        # Use unified template from future_sections app
        template = 'future_sections/teaching_course.html'

        context = get_user_context(request)

        return render(request, template, {
            'teacher_course_teaching_form': teacher_course_teaching_form,
            'teaching_formset': teaching_formset,
            'teacher_course': teacher_course,
            'academic_year': academic_year,
            'teaching_message': fs_config.get('teaching_message', 'change me'),
            'form_config': form_config,
            'form_action_url': request.build_absolute_uri(),
            'is_admin': context['is_admin'],
        })

    @action(detail=False, methods=['get', 'post'], url_path='mark-not-teaching')
    def mark_not_teaching(self, request):
        """
        Mark a course as not being taught for an academic year.
        """
        # Handle both GET (form params) and POST (data params)
        if request.method == 'GET':
            course_certificate_id = request.GET.get('course_certificate_id')
            academic_year_id = request.GET.get('academic_year_id')
        else:
            course_certificate_id = request.data.get('course_certificate_id')
            academic_year_id = request.data.get('academic_year_id')

        if not course_certificate_id or not academic_year_id:
            return Response({
                'status': 'error',
                'message': 'course_certificate_id and academic_year_id are required'
            }, status=400)

        teacher_course = get_object_or_404(
            TeacherCourseCertificate,
            certificate_id=course_certificate_id
        )
        academic_year = get_object_or_404(AcademicYear, pk=academic_year_id)

        # Verify access based on user role
        validate_certificate_access(request, teacher_course)

        highschool_id = teacher_course.teacher_highschool.highschool.id
        fp = get_or_create_future_projection(highschool_id, request.user)

        future_course = FutureCourse.get_or_add(
            teacher_course,
            academic_year,
            {'teaching': 'no'},
            submitter=request.user
        )

        if not future_course.meta:
            future_course.meta = {'fp': str(fp.id), 'history': []}

        add_history_entry(future_course, request.user, 'Marked as not teaching')
        future_course.save()

        add_history_entry(fp, request.user, f'Marked as not teaching course {future_course}')
        fp.save()

        return Response({
            'display': 'swal',
            'status': 'success',
            'message': 'Successfully marked course as not teaching',
            'action': 'reload_future_courses'
        })

    @action(detail=False, methods=['get', 'post', 'delete'], url_path='remove-teaching-status')
    def remove_teaching_status(self, request):
        """
        Remove teaching/not-teaching status for a course.
        """
        # Handle both GET (form params) and POST/DELETE (data params)
        if request.method == 'GET':
            course_certificate_id = request.GET.get('course_certificate_id')
            academic_year_id = request.GET.get('academic_year_id')
        else:
            course_certificate_id = request.data.get('course_certificate_id')
            academic_year_id = request.data.get('academic_year_id')

        if not course_certificate_id or not academic_year_id:
            return Response({
                'status': 'error',
                'message': 'course_certificate_id and academic_year_id are required'
            }, status=400)

        # Check teacher course exists and user has access
        teacher_course = get_object_or_404(
            TeacherCourseCertificate,
            certificate_id=course_certificate_id
        )

        # Verify access based on user role
        validate_certificate_access(request, teacher_course)

        future_course_qs = FutureCourse.objects.filter(
            teacher_course__certificate_id=course_certificate_id,
            academic_year__id=academic_year_id
        )

        if future_course_qs.exists():
            future_course = future_course_qs.first()
            fp_id = future_course.meta.get('fp') if future_course.meta else None

            if fp_id:
                fp = FutureProjection.objects.filter(pk=fp_id).first()
                if fp:
                    add_history_entry(fp, request.user, f'Removed course info {future_course}')
                    fp.save()

            future_course_qs.delete()

        return Response({
            'display': 'swal',
            'status': 'success',
            'message': 'Successfully removed course information',
            'action': 'reload_future_courses'
        })

    @action(detail=False, methods=['get', 'post'], url_path='add-teacher')
    def add_teacher(self, request):
        """
        Add a new teacher course certificate.

        Note: For instructors, this is filtered to only allow adding
        courses they are certified for.
        """
        # Handle both GET (form params) and POST (data params)
        if request.method == 'GET':
            academic_year_id = request.GET.get('academic_year_id')
            course_type = request.GET.get('course_type', 'pathways')
        else:
            academic_year_id = request.data.get('academic_year_id')
            course_type = request.data.get('course_type', 'pathways')

        if not academic_year_id:
            return Response({
                'status': 'error',
                'message': 'academic_year_id is required'
            }, status=400)

        fs_config = get_fs_config()
        academic_year = get_object_or_404(AcademicYear, pk=academic_year_id)
        form = AddNewTeacherForm(request, academic_year, course_type)

        if request.method == 'POST':
            form = AddNewTeacherForm(request, academic_year, course_type, data=request.POST)

            if form.is_valid():
                record = form.save(request, academic_year)

                if record.teacher_course.status in fs_config.get('create_new_instructor_app', []):
                    record.create_teacher_application()

                # Ensure FutureProjection exists
                highschool_id = record.teacher_course.teacher_highschool.highschool.id
                get_or_create_future_projection(highschool_id, request.user)

                return Response({
                    'status': 'Success',
                    'message': 'Successfully added course',
                    'action': 'reload'
                })
            else:
                return Response({
                    'message': 'Please correct the errors and try again.',
                    'details': '',
                    'errors': form.errors.as_json(),
                    'status': 'error'
                }, status=400)

        # Use unified template from future_sections app
        template = 'future_sections/add_new_teacher.html'

        context = get_user_context(request)

        return render(request, template, {
            'academic_year': academic_year,
            'form': form,
            'new_teacher_message': fs_config.get('new_teacher_message', 'change me'),
            'form_action_url': request.build_absolute_uri(),
            'is_admin': context['is_admin'],
        })

    @action(detail=False, methods=['post'], url_path='confirm-sections')
    def confirm_sections(self, request):
        """
        Confirm class sections for highschools.

        POST: Validates and saves the confirmation
        """
        context = get_user_context(request)

        form = ConfirmClassSectionsForm(
            highschools=context['highschools'],
            action=request.data.get('action', 'confirmed_class_sections'),
            data=request.data
        )

        if form.is_valid():
            form.save(request)

            # Send confirmation email to the HS admin
            self._send_confirmation_email(request, form.cleaned_data)

            return Response({
                'status': 'success',
                'message': 'Successfully confirmed class sections'
            })

        return Response({
            'status': 'error',
            'message': 'Please fix the errors and try again.',
            'errors': form.errors.as_json()
        }, status=400)

    def _send_confirmation_email(self, request, cleaned_data):
        """
        Send confirmation email to the HS admin after they confirm sections.
        """
        logger = logging.getLogger(__name__)

        fs_config = get_fs_config()

        subject_template = fs_config.get('confirmation_subject', '')
        message_template = fs_config.get('confirmation_message', '')

        if not subject_template or not message_template:
            return

        academic_year = cleaned_data.get('academic_year')
        highschools = cleaned_data.get('highschools')

        for highschool in highschools:
            # Get all FutureCourse records for this highschool and academic year
            future_courses = FutureCourse.objects.filter(
                academic_year=academic_year,
                teacher_course__teacher_highschool__highschool=highschool
            ).select_related(
                'teacher_course__course',
                'teacher_course__teacher_highschool__highschool',
                'teacher_course__teacher_highschool__teacher__user',
            )

            # Build the future_sections summary as an HTML table
            future_sections_text = self._build_future_sections_table(future_courses)

            context = Context({
                'future_sections': mark_safe(future_sections_text),
                'academic_year': str(academic_year),
                'admin_first_name': request.user.first_name,
                'admin_last_name': request.user.last_name,
                'highschool': highschool.name,
            })

            # Render subject and message
            subject = Template(subject_template).render(context)
            text_body = Template(message_template).render(context)

            html_template = get_template('cis/email.html')
            html_body = html_template.render({'message': text_body})

            to = [request.user.email]
            if getattr(django_settings, 'DEBUG', True):
                to = ['kadaji@gmail.com']

            try:
                send_html_mail(
                    subject,
                    text_body,
                    html_body,
                    django_settings.DEFAULT_FROM_EMAIL,
                    to
                )
                logger.info(f'Sent confirmation email to {to} for {highschool.name}')
            except Exception as e:
                logger.error(f'Failed to send confirmation email: {e}')

    @staticmethod
    def _build_future_sections_table(future_courses):
        """
        Build an HTML table summarizing future sections for an email.
        """
        rows = ""
        for fc in future_courses:
            course_name = str(fc.teacher_course.course)
            highschool_name = fc.teacher_course.teacher_highschool.highschool.name
            instructor = str(fc.teacher_course.teacher_highschool.teacher)

            if fc.section_info and fc.section_info.get('teaching') == 'yes':
                status = "Teaching"
                details = ", ".join(fc.section_display) if fc.section_display else ""
            elif fc.section_info and fc.section_info.get('teaching') == 'no':
                status = "Not Teaching"
                details = ""
            else:
                status = "—"
                details = ""

            rows += (
                f"<tr>"
                f"<td style='padding:6px;border:1px solid #ddd;'>{course_name}</td>"
                f"<td style='padding:6px;border:1px solid #ddd;'>{highschool_name}</td>"
                f"<td style='padding:6px;border:1px solid #ddd;'>{instructor}</td>"
                f"<td style='padding:6px;border:1px solid #ddd;'>{status}</td>"
                f"<td style='padding:6px;border:1px solid #ddd;'>{details}</td>"
                f"</tr>"
            )

        return (
            "<table style='border-collapse:collapse;width:100%;'>"
            "<tr>"
            "<th style='padding:6px;border:1px solid #ddd;text-align:left;background:#f5f5f5;'>Course</th>"
            "<th style='padding:6px;border:1px solid #ddd;text-align:left;background:#f5f5f5;'>High School</th>"
            "<th style='padding:6px;border:1px solid #ddd;text-align:left;background:#f5f5f5;'>Instructor</th>"
            "<th style='padding:6px;border:1px solid #ddd;text-align:left;background:#f5f5f5;'>Status</th>"
            "<th style='padding:6px;border:1px solid #ddd;text-align:left;background:#f5f5f5;'>Details</th>"
            "</tr>"
            f"{rows}"
            "</table>"
        )

    @action(detail=False, methods=['post'], url_path='confirm-administrators')
    def confirm_administrators(self, request):
        """
        Confirm school administrators for highschools.

        POST: Validates and saves the confirmation
        """
        context = get_user_context(request)

        form = ConfirmHighSchoolAdministratorsForm(
            highschools=context['highschools'],
            data=request.data
        )

        if form.is_valid():
            form.save(request)
            return Response({
                'status': 'success',
                'message': 'Successfully confirmed school administrators'
            })

        return Response({
            'status': 'error',
            'message': 'Please fix the errors and try again.',
            'errors': form.errors.as_json()
        }, status=400)


class CourseRequestViewSet(viewsets.ViewSet):
    """
    API ViewSet for course requests - TeacherCourseCertificate with offering status.

    Provides role-aware queryset:
    - HS Admin: All certificates for their highschools
    - Instructor: Only their own certificates
    """
    permission_classes = [IsHSAdminOrInstructor]

    def get_queryset(self):
        return get_course_certificates_for_user(self.request).select_related(
            'course',
            'teacher_highschool__teacher__user',
            'teacher_highschool__highschool'
        )

    def list(self, request, *args, **kwargs):
        """Return course requests with merged offering status from FutureCourse."""
        from cis.models.section import ClassSection
        from cis.models.term import Term
        from django.db.models import Count

        fs_config = get_fs_config()
        academic_year_id = fs_config.get('academic_year')
        academic_year = AcademicYear.objects.filter(pk=academic_year_id).first()
        previous_academic_year_id = fs_config.get('previous_academic_year')
        window_is_open = FutureCourse.is_window_open()

        # Get course certificates
        queryset = self.get_queryset()

        # Build lookup of FutureCourse by teacher_course certificate_id
        future_courses = FutureCourse.objects.filter(
            teacher_course__in=queryset,
            academic_year=academic_year
        ).select_related('teacher_course')

        offering_lookup = {}
        for fc in future_courses:
            offering_lookup[str(fc.teacher_course.certificate_id)] = {
                'teaching': fc.section_info.get('teaching') if fc.section_info else None,
                'sections': fc.section_info.get('sections', []) if fc.section_info else [],
                'section_display': fc.section_display,  # Pre-formatted display from settings
            }

        # Build previous year section counts per (course, highschool, term)
        prev_year_lookup = {}
        if previous_academic_year_id:
            prev_sections = (
                ClassSection.objects.filter(
                    term__academic_year__id=previous_academic_year_id,
                    status='active',
                )
                .values('course_id', 'highschool_id', 'term__id', 'term__label')
                .annotate(count=Count('id'))
            )
            for row in prev_sections:
                key = f"{row['course_id']}_{row['highschool_id']}"
                prev_year_lookup.setdefault(key, []).append({
                    'term_name': row['term__label'],
                    'count': row['count'],
                })

        # Build response data
        course_display_template = fs_config.get('course_display_template', '{course_title}')
        data = []
        for course in queryset:
            cert_id = str(course.certificate_id)
            offering = offering_lookup.get(cert_id, {})

            try:
                course_display = course_display_template.format(
                    course_name=course.course.name or '',
                    course_title=course.course.title,
                    credit_hours=course.course.credit_hours,
                )
            except (KeyError, IndexError):
                course_display = course.course.title

            # Previous year sections for this course + highschool
            prev_key = f"{course.course_id}_{course.teacher_highschool.highschool_id}"
            prev_year_sections = prev_year_lookup.get(prev_key, [])

            data.append({
                'certificate_id': cert_id,
                'course_title': course_display,
                'teacher_name': str(course.teacher_highschool.teacher),
                'status': course.status,
                'highschool_name': course.teacher_highschool.highschool.name,
                'academic_year_id': str(academic_year.id) if academic_year else None,
                'window_is_open': window_is_open,
                'offering_status': offering.get('teaching'),
                'sections': offering.get('sections', []),
                'section_display': offering.get('section_display', []),
                'prev_year_sections': prev_year_sections,
            })

        return Response(data)


class AdminPositionViewSet(viewsets.ViewSet):
    """
    API ViewSet for administrator positions - returns all highschool/role combinations.

    Provides role-aware access for managing school personnel positions.
    """
    permission_classes = [IsHSAdminOrInstructor]

    def list(self, request, *args, **kwargs):
        """Return all highschool x role combinations, including empty slots."""
        from cis.models.highschool_administrator import HSPosition

        role_ids = request.GET.getlist('role_ids')
        context = get_user_context(request)
        highschools = context['highschools']
        roles = HSPosition.objects.filter(id__in=role_ids) if role_ids else HSPosition.objects.none()

        # Get existing positions
        existing_qs = HSAdministratorPosition.objects.filter(
            status__iexact='active',
            highschool__in=highschools
        )
        if role_ids:
            existing_qs = existing_qs.filter(position__id__in=role_ids)
        existing_qs = existing_qs.select_related('hsadmin__user', 'highschool', 'position')

        # Build lookup of existing positions by highschool_id + position_id
        existing_positions = {}
        for pos in existing_qs:
            key = f"{pos.highschool_id}_{pos.position_id}"
            existing_positions[key] = pos

        # Generate all combinations
        data = []
        for highschool in highschools:
            for role in roles:
                key = f"{highschool.id}_{role.id}"
                pos = existing_positions.get(key)

                if pos:
                    data.append({
                        'id': str(pos.id),
                        'highschool_id': str(pos.highschool_id),
                        'highschool_name': pos.highschool.name,
                        'position_id': str(pos.position_id),
                        'position_name': pos.position.name,
                        'admin_name': f"{pos.hsadmin.user.last_name}, {pos.hsadmin.user.first_name}",
                        'admin_email': pos.hsadmin.user.email,
                        'status': pos.status,
                    })
                else:
                    data.append({
                        'id': None,
                        'highschool_id': str(highschool.id),
                        'highschool_name': highschool.name,
                        'position_id': str(role.id),
                        'position_name': role.name,
                        'admin_name': None,
                        'admin_email': None,
                        'status': None,
                    })

        return Response(data)

    @action(detail=False, methods=['get', 'post'], url_path='assign')
    def assign(self, request):
        """Assign an administrator to a highschool/role position."""
        if request.method == 'GET':
            highschool_id = request.GET.get('highschool_id')
            role_id = request.GET.get('role_id')
            administrator_id = request.GET.get('administrator_id')
        else:
            highschool_id = request.data.get('highschool_id') or request.data.get('highschool')
            role_id = request.data.get('role_id') or request.data.get('position')
            administrator_id = request.data.get('administrator_id') or request.data.get('administrator')

        if not highschool_id or not role_id:
            return Response({
                'status': 'error',
                'message': 'highschool_id and role_id are required'
            }, status=400)

        # Verify user has access to this highschool
        context = get_user_context(request)
        highschools = context['highschools']
        highschool = get_object_or_404(HighSchool, pk=highschool_id)
        if highschool not in highschools:
            raise PermissionDenied("No access to this highschool")

        fs_config = get_fs_config()
        form = HSAdministratorPositionForm(request, highschool_id, role_id, administrator_id)

        if request.method == 'POST':
            # Ensure FutureProjection exists for tracking
            get_or_create_future_projection(highschool_id, request.user)

            form = HSAdministratorPositionForm(
                request, highschool_id, role_id, administrator_id, data=request.POST
            )

            if form.is_valid():
                form.save(request)
                return Response({
                    'status': 'Success',
                    'message': 'Successfully assigned high school administrator',
                    'action': 'reload_table'
                })
            else:
                return Response({
                    'message': 'Please correct the errors and try again.',
                    'details': '',
                    'errors': form.errors.as_json(),
                    'status': 'error'
                }, status=400)

        context = {
            'form': form,
            'new_teacher_message': fs_config.get('edit_role_message', 'change me'),
            'form_action_url': request.build_absolute_uri(),
        }
        return render(request, 'future_sections/add_new_teacher.html', context)
