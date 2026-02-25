"""
CE Portal Views for Future Sections
"""
import json

from django.conf import settings as s
from django.db import IntegrityError
from django.contrib import messages
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.forms.formsets import formset_factory
from django.template.loader import get_template
from django.utils.safestring import mark_safe
from django.views.decorators.clickjacking import xframe_options_exempt

from mailer import send_html_mail

from cis.forms.future_sections import (
    TeacherCourseBaseLinkFormSet,
    TeacherCourseSectionForm,
    TeacherCourseTeachingForm,
    SearchInstructorByCohortForm
)

from cis.models.teacher import Teacher, TeacherCourseCertificate
from cis.models.term import AcademicYear, Term
from cis.models.settings import Setting
from cis.models.course import Cohort

from ..models import FutureCourse, FutureSection, FutureProjection
from ..settings.future_sections import future_sections as fs_settings

from cis.menu import cis_menu, draw_menu


def delete_section(request):
    """Delete a future section"""
    section_id = request.GET.get('section')
    future_section = get_object_or_404(FutureSection, pk=section_id)

    future_section.delete()
    return JsonResponse({'status': 'success'})


def future_sections_actions(request):
    """AJAX handler for future sections actions"""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'teaching-section':
            return mark_as_teaching(
                request,
                request.POST.get('teacher_course_certificate_id'),
                request.POST.get('academic_year_id')
            )

    if request.method == 'GET':
        action = request.GET.get('action')

        if action == 'remove-not-teaching-section':
            return remove_marked_as_not_teaching(
                request,
                request.GET.get('course_certificate'),
                request.GET.get('academic_year_id')
            )
        elif action == 'not-teaching-section':
            return mark_as_not_teaching(
                request,
                request.GET.get('course_certificate'),
                request.GET.get('academic_year_id')
            )
        elif action == 'teaching-section':
            return mark_as_teaching(
                request,
                request.GET.get('course_certificate'),
                request.GET.get('academic_year_id')
            )


def mark_as_teaching(request, course_certificate_id, academic_year_id):
    """Mark a course as teaching with section details"""
    teacher_course = get_object_or_404(
        TeacherCourseCertificate,
        certificate_id=course_certificate_id
    )

    academic_year = get_object_or_404(
        AcademicYear,
        pk=academic_year_id
    )

    TeachingFormSet = formset_factory(
        TeacherCourseSectionForm,
        formset=TeacherCourseBaseLinkFormSet,
        extra=1
    )

    future_course = FutureCourse.get_or_add(
        teacher_course,
        academic_year,
        submitter=request.user
    )

    if future_course.section_info == {}:
        future_course.section_info = {
            'teaching': 'yes',
            'sections': []
        }
        future_course.save()

    if future_course.section_info:
        initial_data = future_course.section_info.get('sections')
    else:
        initial_data = []

    if request.method == 'POST':
        teacher_course_teaching_form = TeacherCourseTeachingForm(
            request.POST
        )

        teaching_formset = TeachingFormSet(request.POST)

        if teacher_course_teaching_form.is_valid() and teaching_formset.is_valid():
            section_info = []
            for teaching_form in teaching_formset:
                if teaching_form.cleaned_data:
                    data = teaching_form.cleaned_data
                    if data.get('term'):
                        section_info.append({
                            'term_name': str(teaching_form.cleaned_data.get('term')),
                            'term': str(teaching_form.cleaned_data.get('term').id),
                            'method_of_payment': teaching_form.cleaned_data.get('method_of_payment'),
                            'number_of_sections': teaching_form.cleaned_data.get('number_of_sections')
                        })

            future_course.section_info = {'teaching': 'yes', 'sections': section_info}
            future_course.save()

            data = {
                'status': 'Success',
                'message': 'Successfully saved course information',
                'action': 'reload_table'
            }
            return JsonResponse(data)
        else:
            errors = {}
            index = 0
            for err in teaching_formset.errors:
                for field, error_message in err.items():
                    errors[
                        "form-" + str(index) + "-" + field
                    ] = [{
                        'message': error_message
                    }]

                index += 1

            return JsonResponse({
                'message': 'Please correct the errors and try again.',
                'details': mark_safe(str(teaching_formset.non_form_errors())),
                'errors': json.dumps(errors),
                'status': 'error'
            }, status=400)
    else:
        teacher_course_teaching_form = TeacherCourseTeachingForm(
            initial={
                'teacher_course_certificate_id': teacher_course.certificate_id,
                'academic_year_id': academic_year.id
            }
        )

        teaching_formset = TeachingFormSet(
            initial=initial_data
        )

    fs_config = fs_settings.from_db()

    # Parse form config for dynamic field rendering
    import json
    try:
        form_config = json.loads(fs_config.get('teaching_form_config', '{}'))
    except (json.JSONDecodeError, TypeError):
        form_config = {}

    # Set defaults if not configured
    if 'fields' not in form_config:
        form_config['fields'] = ['term']
    if 'show_syllabus' not in form_config:
        form_config['show_syllabus'] = False

    context = {
        'teacher_course_teaching_form': teacher_course_teaching_form,
        'teaching_formset': teaching_formset,
        'teacher_course': teacher_course,
        'academic_year': academic_year,
        'teaching_message': fs_config.get('teaching_message', 'change me'),
        'form_action_url': '/ce/future_sections/ajax',
        'form_config': form_config,
    }

    return render(request, 'future_sections/teaching_course.html', context)


def remove_marked_as_not_teaching(request, course_certificate_id, academic_year_id):
    """Remove the not teaching designation"""
    future_course = FutureCourse.objects.filter(
        teacher_course__certificate_id=course_certificate_id,
        academic_year__id=academic_year_id
    ).delete()

    data = {
        'display': 'swal',
        'status': 'success',
        'message': 'Successfully removed course information',
        'action': 'reload_future_courses'
    }
    return JsonResponse(data)


def mark_as_not_teaching(request, course_certificate_id, academic_year_id):
    """Mark a course as not being taught"""
    teacher_course = get_object_or_404(
        TeacherCourseCertificate,
        certificate_id=course_certificate_id
    )

    academic_year = get_object_or_404(
        AcademicYear,
        pk=academic_year_id
    )

    future_course = FutureCourse.get_or_add(
        teacher_course,
        academic_year,
        {
            'teaching': 'no'
        },
        submitter=request.user
    )

    data = {
        'display': 'swal',
        'status': 'success',
        'message': 'Successfully marked course as not teaching',
        'action': 'reload_future_courses'
    }
    return JsonResponse(data)


def send_survey_to_instructors(request, instructors=[]):
    """Send survey emails to instructors"""
    subject = Setting.get_value("cis_future_sections", "email_subject")
    message = Setting.get_value("cis_future_sections", "email_message")
    message_replyto = Setting.get_value("cis_future_sections", "message_replyto")
    academic_year = AcademicYear.objects.get(
        pk=Setting.get_value("cis_future_sections", "academic_year"))

    term = Term.objects.get(
        pk=Setting.get_value("cis_future_sections", "term"))

    bulk_messages = []
    email_summary = []
    for instructor in instructors:
        mesg = message
        instructor = Teacher.objects.get(pk=instructor)

        if not instructor:
            continue

        mesg = mesg.replace("{{instructor_first_name}}", instructor.user.first_name)
        mesg = mesg.replace("{{academic_year}}", academic_year.name)
        mesg = mesg.replace("{{term}}", str(term))
        mesg = mesg.replace(
            "{{course_schedule_link}}",
            request.scheme + "://" + request.get_host() + "/instructor/course_schedule/" + str(instructor.id))

        if Setting.get_value("cis_future_sections", "mode") == "active":
            to = [instructor.user.secondary_email]
        else:
            to = Setting.get_value("cis_future_sections", 'testers').split(",")

        send_to = to
        text_body = mesg

        template = get_template('cis/email.html')
        html_body = template.render({
            'message': text_body
        })

        send_html_mail(
            subject,
            text_body,
            html_body,
            s.DEFAULT_FROM_EMAIL,
            send_to
        )

        email_summary.append(f"{to} sent")

    return JsonResponse({
        'status': 'SUCCESS',
        'message': f"Successfully processed your request. A summary has been sent to testers"})


def settings(request):
    """Settings page for future sections"""
    template = 'future_sections/ce/settings.html'
    key = "cis_future_sections"

    try:
        setting = Setting.objects.get(key=key)
    except Setting.DoesNotExist:
        setting = Setting()
        setting.key = key
        setting.value = {}

    search_instructor_form = SearchInstructorByCohortForm()
    instructors = []

    if request.method == 'POST':
        if request.POST.get('action', '') == "send_course_schedule_survey":
            return send_survey_to_instructors(request, request.POST.getlist('send_to[]'))

        if request.POST.get('get_instructors', '') == "Get Instructors":
            search_instructor_form = SearchInstructorByCohortForm(request.POST)
            if search_instructor_form.is_valid():
                all_instructors = Cohort.get_instructor_certificates(
                    search_instructor_form.cleaned_data['cohort'],
                    search_instructor_form.cleaned_data.get('highschool_term_type')
                )

                # Filter by teacher course status, and course status
                all_instructors = all_instructors.filter(
                    status__in=Setting.get_value("cis_future_sections", "teacher_course_status")
                )

                all_instructors = all_instructors.filter(
                    course__status__in=Setting.get_value("cis_future_sections", "course_status")
                )

                instructors = all_instructors.distinct(
                    'teacher_highschool__teacher')

                # check if all courses has been responded to, if so remove instructor
                fs_academic_year = Setting.get_value("cis_future_sections", "academic_year")
                fs_term = Setting.get_value("cis_future_sections", "term")

                for instructor in instructors:
                    future_course = FutureCourse.objects.filter(
                        teacher=instructor.teacher_highschool.teacher,
                        term=fs_term
                    )
                    if future_course and future_course[0].has_completed_all_courses():
                        instructors = instructors.exclude(
                            teacher_highschool__teacher=instructor.teacher_highschool.teacher)
            else:
                messages.add_message(
                    request,
                    messages.SUCCESS,
                    'Select at least one cohort and try again',
                    'list-group-item-danger')
        else:
            # Note: FutureSectionForm is not defined - this appears to be legacy code
            # that was never fully implemented. The settings form is now managed
            # through the setting app at /setting/run_record/<setting_id>
            pass

    form = fs_settings(request, initial={
        'academic_year': setting.value.get('academic_year'),
        'term': setting.value.get('term'),
        'starting_date': setting.value.get('starting_date'),
        'ending_date': setting.value.get('ending_date'),
        'course_status': setting.value.get('course_status'),
        'teacher_course_status': setting.value.get('teacher_course_status'),
        'message_replyto': setting.value.get('message_replyto'),
        'email_subject': setting.value.get('email_subject'),
        'email_message': setting.value.get('email_message'),
        'confirmation_subject': setting.value.get('confirmation_subject'),
        'confirmation_message': setting.value.get('confirmation_message'),
        'mode': setting.value.get('mode'),
        'testers': setting.value.get('testers'),
        'welcome_message': setting.value.get('welcome_message'),
        'teaching_message': setting.value.get('teaching_message'),
        'not_teaching_message': setting.value.get('not_teaching_message')
    })

    if len(instructors) <= 0:
        instructors = []
    return render(
        request,
        template, {
            'form': form,
            'search_form': search_instructor_form,
            'instructors': instructors,
            'page_title': "Settings",
            'labels': {
                'all_items': 'All Future Sections'
            },
            'urls': {
                'all_items': 'cis:future_sections'
            },
            'menu': draw_menu(cis_menu, 'classes', 'future_sections')
        })


def index(request):
    """Future section search and index page for CE staff"""
    menu = draw_menu(cis_menu, 'classes', 'future_sections')
    template = 'future_sections/ce/index.html'
    key = "cis_future_sections"

    try:
        setting = Setting.objects.get(key=key)
    except Setting.DoesNotExist:
        setting = Setting()
        setting.key = key
        setting.value = {}

    try:
        active_academic_year = AcademicYear.objects.get(pk=setting.value.get('academic_year'))
    except:
        active_academic_year = AcademicYear.objects.last()

    return render(
        request,
        template, {
            'menu': menu,
            'page_title': 'Course Requests',
            'api_url': '/ce/future_sections/api/future_class_section?format=datatables',
            'future_projections_url': '/ce/future_sections/api/future_projection?format=datatables',
            'pending_api_url': '/ce/future_sections/api/pending_future_class_sections?format=datatables',
            'notification_log_api_url': '/ce/future_sections/api/notification_logs/?format=datatables',
            'active_academic_year': active_academic_year,
            'academic_years': AcademicYear.objects.all().order_by('-name')
        }
    )


@xframe_options_exempt
def detail(request, record_id):
    """Record details page"""
    pass


def get_highschool_admins(request):
    """Return active HS administrators for a given highschool."""
    from cis.models.highschool import HighSchool
    from cis.models.highschool_administrator import HSAdministratorPosition

    highschool_id = request.GET.get('highschool_id')
    if not highschool_id:
        return JsonResponse({'status': 'error', 'message': 'Missing highschool_id'}, status=400)

    highschool = get_object_or_404(HighSchool, pk=highschool_id)

    admins = HSAdministratorPosition.objects.filter(
        highschool=highschool,
        status='Active'
    ).select_related('hsadmin__user', 'position')

    data = []
    seen_emails = set()
    for admin_pos in admins:
        user = admin_pos.hsadmin.user
        email = user.email
        if not email or email in seen_emails:
            continue
        seen_emails.add(email)
        data.append({
            'id': str(admin_pos.id),
            'name': f'{user.first_name} {user.last_name}',
            'email': email,
            'position': str(admin_pos.position),
        })

    return JsonResponse({'status': 'success', 'admins': data, 'highschool': highschool.name})


def send_pending_reminder(request):
    """Send pending section request reminder email to selected admins at a specific highschool."""
    import logging
    from django.template import Context, Template
    from cis.models.highschool import HighSchool
    from cis.models.highschool_administrator import HSAdministratorPosition
    from cis.models.term import AcademicYear

    logger = logging.getLogger(__name__)

    highschool_id = request.GET.get('highschool_id')
    academic_year_id = request.GET.get('academic_year_id')
    admin_ids = request.GET.getlist('admin_ids[]')

    if not highschool_id or not academic_year_id or not admin_ids:
        return JsonResponse({
            'status': 'error',
            'action': 'display',
            'message': 'Missing required parameters.'
        }, status=400)

    highschool = get_object_or_404(HighSchool, pk=highschool_id)
    fs_config = fs_settings.from_db()

    subject = fs_config.get('pending_notification_subject', 'Reminder: Section Request Response Needed')
    message_template = fs_config.get('pending_notification_message', '')

    if not message_template:
        return JsonResponse({
            'status': 'error',
            'action': 'display',
            'message': 'Pending notification message template is not configured in settings.'
        })

    # Count pending courses for this highschool
    received_ids = FutureCourse.objects.filter(
        academic_year__id=academic_year_id
    ).values_list('teacher_course__certificate_id', flat=True)

    pending_count = TeacherCourseCertificate.objects.filter(
        teacher_highschool__highschool=highschool,
        course__status__in=fs_config.get('course_status', []),
        status__in=fs_config.get('teacher_course_status', [])
    ).exclude(
        certificate_id__in=received_ids
    ).count()

    # Get academic year name
    try:
        academic_year = AcademicYear.objects.get(id=academic_year_id)
        academic_year_name = str(academic_year)
    except AcademicYear.DoesNotExist:
        academic_year_name = ''

    # Get only the selected admins
    admins = HSAdministratorPosition.objects.filter(
        id__in=admin_ids,
        highschool=highschool,
        status='Active'
    ).select_related('hsadmin__user')

    site_url = getattr(s, 'SITE_URL', '')
    link = f"{site_url}/highschool_admin/future_sections/"

    emails_sent = 0
    seen_emails = set()

    for admin_pos in admins:
        user = admin_pos.hsadmin.user
        email = user.email

        if not email or email in seen_emails:
            continue
        seen_emails.add(email)

        try:
            template_obj = Template(message_template)
            context = Context({
                'admin_first_name': user.first_name,
                'admin_last_name': user.last_name,
                'highschool': highschool.name,
                'academic_year': academic_year_name,
                'pending_count': pending_count,
                'link': link,
            })
            text_body = template_obj.render(context)

            html_template = get_template('cis/email.html')
            html_body = html_template.render({'message': text_body})

            to = [email]
            if getattr(s, 'DEBUG', True):
                to = ['kadaji@gmail.com']

            send_html_mail(
                subject,
                text_body,
                html_body,
                s.DEFAULT_FROM_EMAIL,
                to
            )
            emails_sent += 1
        except Exception as e:
            logger.error(f'Failed to send pending reminder to {email}: {e}')

    return JsonResponse({
        'status': 'success',
        'action': 'display',
        'title': 'Email Sent',
        'message': f'Sent reminder to {emails_sent} administrator(s) at {highschool.name}.'
    })


def bulk_actions(request):
    """Handle bulk actions for future courses"""
    action = request.GET.get('action')

    if action == 'mark_as_reviewed':
        return mark_as_reviewed(request)

    if action == 'mark_as_submitted':
        return mark_as_submitted(request)

    # Default response for unknown actions
    return JsonResponse({
        'status': 'error',
        'title': 'Error',
        'message': 'Unknown action',
        'action': 'display'
    })


def mark_as_reviewed(request):
    """Mark selected future courses as reviewed"""
    ids = request.GET.getlist('ids[]')

    if not ids:
        return JsonResponse({
            'status': 'warning',
            'title': 'No Selection',
            'message': 'Please select at least one record.',
            'action': 'display'
        })

    # Update the status of selected records
    updated_count = FutureCourse.objects.filter(
        id__in=ids
    ).update(status='reviewed')

    return JsonResponse({
        'status': 'success',
        'title': 'Success',
        'message': f'Successfully marked {updated_count} request(s) as reviewed.',
        'action': 'display'
    })


def mark_as_submitted(request):
    """Mark selected future courses as submitted (reset status)"""
    ids = request.GET.getlist('ids[]')

    if not ids:
        return JsonResponse({
            'status': 'warning',
            'title': 'No Selection',
            'message': 'Please select at least one record.',
            'action': 'display'
        })

    # Update the status of selected records
    updated_count = FutureCourse.objects.filter(
        id__in=ids
    ).update(status='submitted')

    return JsonResponse({
        'status': 'success',
        'title': 'Success',
        'message': f'Successfully marked {updated_count} request(s) as submitted.',
        'action': 'display'
    })
