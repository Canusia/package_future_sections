"""
CE Portal Views for Future Sections
"""
import json
import logging
import uuid

from django.conf import settings as s
from django.db import IntegrityError
from django.contrib import messages
from django.shortcuts import get_object_or_404, render
from django.http import Http404, JsonResponse
from django.forms.formsets import formset_factory
from django.template.loader import get_template
from django.utils.safestring import mark_safe
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST

from mailer import send_html_mail

from ..forms import (
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
from ..utils import build_initial_from_prev_year, build_section_info_from_formset

from cis.menu import cis_menu, draw_menu

logger = logging.getLogger(__name__)


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

        if action == 'email-new-teacher':
            return email_new_teacher(request)

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
        elif action == 'email-new-teacher':
            return email_new_teacher(request)


def email_new_teacher(request):
    """Compose and send an email to the new teacher named on a section."""
    from django.conf import settings as django_settings
    from django.template import Context, Template
    from django.template.loader import get_template
    from django.urls import reverse as url_reverse
    from mailer import send_html_mail

    from ..forms import EmailNewTeacherForm
    from ..settings.future_sections import (
        DEFAULT_NEW_TEACHER_EMAIL_SUBJECT,
        DEFAULT_NEW_TEACHER_EMAIL_MESSAGE,
    )
    from ..utils import add_history_entry, get_fs_config

    source = request.POST if request.method == 'POST' else request.GET
    future_course_id = source.get('future_course_id')
    # Guard a client-supplied future_course_id: a non-UUID value (fuzzing, a
    # stale/uninitialised form field) would raise ValidationError -> 500 in
    # the pk lookup below. Same idiom as the PT-1 term_id guard (see
    # cis/views/teacher.py).
    try:
        uuid.UUID(str(future_course_id))
    except (ValueError, AttributeError, TypeError):
        raise Http404('Invalid future_course_id')
    future_course = get_object_or_404(FutureCourse, pk=future_course_id)
    fs_config = get_fs_config()

    sections = (future_course.section_info or {}).get('sections') or []
    try:
        index = int(source.get('section_index', 0))
    except (TypeError, ValueError):
        index = -1
    section = sections[index] if 0 <= index < len(sections) else {}

    teacher_course = future_course.teacher_course
    highschool = teacher_course.teacher_highschool.highschool
    start_app_url = request.build_absolute_uri(
        url_reverse('applicant_app:start_app'))

    context_values = {
        'new_teacher_name': section.get('new_teacher_name', ''),
        'course': str(teacher_course.course),
        'highschool': highschool.name,
        'academic_year': str(future_course.academic_year),
        'current_teacher_name': str(teacher_course.teacher_highschool.teacher),
        'term_name': section.get('term_name', ''),
        'link': start_app_url,
    }

    if request.method == 'GET':
        form = EmailNewTeacherForm(
            future_course=future_course,
            initial={
                'section_index': index,
                'recipient': section.get('new_teacher_email', ''),
                'subject': (fs_config.get('new_teacher_email_subject')
                            or DEFAULT_NEW_TEACHER_EMAIL_SUBJECT),
                'message': (fs_config.get('new_teacher_email_message')
                            or DEFAULT_NEW_TEACHER_EMAIL_MESSAGE),
            },
        )
        return render(
            request,
            'future_sections/ce/email_new_teacher.html',
            {
                'form': form,
                'future_course_id': str(future_course.id),
                'form_action_url': url_reverse(
                    'future_sections_ce:future_sections_actions'),
                **context_values,
            },
        )

    form = EmailNewTeacherForm(data=request.POST, future_course=future_course)
    if not form.is_valid():
        return JsonResponse({
            'status': 'error',
            'message': 'Please correct the errors and try again.',
            'errors': form.errors,
        }, status=400)

    data = form.cleaned_data
    recipient = data['recipient']

    if data['mode'] == 'invite':
        from ..utils import ExistingAccountNotApplicantError, get_or_create_applicant
        try:
            applicant, _created = get_or_create_applicant(
                recipient, context_values['new_teacher_name'])
        except ExistingAccountNotApplicantError:
            return JsonResponse({
                'status': 'error',
                'message': (
                    f'{recipient} already belongs to an existing account '
                    'that is not an applicant. Handle this teacher through '
                    'the normal add-teacher route instead.'),
            }, status=400)
        except Exception as exc:
            logger.error('New-teacher invite failed for %s: %s',
                         recipient, exc)
            return JsonResponse({
                'status': 'error',
                'message': ('Could not create the invitation. '
                            'No email was sent.'),
            }, status=400)

        # Point the teacher at the record we just made for them, rather than
        # at start_app — that would ask them to register from scratch and
        # collide with the account created here. This is the same link, to the
        # same address, that send_verification_request_email would have sent,
        # so it carries the same proof-of-control guarantee; sending it inline
        # means one email instead of two saying different things.
        context_values['link'] = applicant.verify_email_url

    context = Context(context_values)
    subject = Template(data['subject']).render(context)
    text_body = Template(data['message']).render(context)
    html_body = get_template('cis/email.html').render({'message': text_body})

    to = [recipient]
    if getattr(django_settings, 'DEBUG', True):
        to = ['kadaji@gmail.com']

    send_html_mail(subject, text_body, html_body,
                   django_settings.DEFAULT_FROM_EMAIL, to)

    add_history_entry(
        future_course, request.user,
        f"Emailed new teacher {recipient} ({data['mode']})"
        f" for {context_values['term_name'] or 'section'}")
    future_course.save()

    return JsonResponse({
        'status': 'Success',
        'display': 'swal',
        'message': f'Email sent to {recipient}.',
        # The compose box submits through `.fs-ajax-form`, whose success
        # handler closes the modal and reloads the table only on
        # 'reload_table'. 'reload_future_courses' is the `.course-action` GET
        # handler's vocabulary and leaves the modal open here.
        'action': 'reload_table',
    })


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

    future_course = FutureCourse.get_or_add(
        teacher_course,
        academic_year,
        submitter=request.user
    )

    is_new = future_course.section_info == {}
    if is_new:
        future_course.section_info = {
            'teaching': 'yes',
            'sections': []
        }
        future_course.save()

    if future_course.section_info:
        initial_data = future_course.section_info.get('sections')
    else:
        initial_data = []

    # Pre-populate from previous year sections for new records
    formset_extra = 1
    if is_new and not initial_data:
        initial_data = build_initial_from_prev_year(teacher_course)
        if initial_data:
            formset_extra = 0

    TeachingFormSet = formset_factory(
        TeacherCourseSectionForm,
        formset=TeacherCourseBaseLinkFormSet,
        extra=formset_extra
    )

    if request.method == 'POST':
        teacher_course_teaching_form = TeacherCourseTeachingForm(
            request.POST
        )

        teaching_formset = TeachingFormSet(request.POST, request.FILES)

        if teacher_course_teaching_form.is_valid() and teaching_formset.is_valid():
            section_info = build_section_info_from_formset(
                request, teaching_formset, future_course,
            )
            future_course.section_info = {'teaching': 'yes', 'sections': section_info}
            future_course.submitted_by = request.user
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

    from ..review.helpers import review_required

    return render(
        request,
        template, {
            'menu': menu,
            'page_title': 'Course Requests',
            'require_review': review_required(),
            'api_url': '/ce/future_sections/api/future_class_section?format=datatables',
            'future_projections_url': '/ce/future_sections/api/future_projection?format=datatables',
            'pending_api_url': '/ce/future_sections/api/pending_future_class_sections?format=datatables',
            'notification_log_api_url': '/ce/future_sections/api/notification_logs/?format=datatables',
            'review_notification_log_api_url': '/ce/future_sections/api/review_notification_logs/?format=datatables',
            'active_academic_year': active_academic_year,
            'academic_years': AcademicYear.objects.all().order_by('-name'),
            'enter_course_details_label': (
                setting.value.get('enter_course_details_label')
                or 'Enter Course Details'),
            'not_teaching_label': (
                setting.value.get('not_teaching_label')
                or 'We are not teaching this course'),
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


@require_POST
def send_review_reminder(request):
    """Send one reviewer a reminder about one outstanding section request.

    Used by the CE reviewers modal's per-reviewer "Send reminder" action.
    All authorization happens server-side in
    `FutureCourse.send_review_reminder`: the client only names a
    (future_course_id, reviewer_id) pair, and the model re-derives whether
    that reviewer actually holds an outstanding slot on the request's live
    round before sending anything.

    POST-only (PT-33-style): sending mail is a state change, so a GET must
    not trigger it -- a cross-site GET navigation or a link-prefetcher
    hitting this URL while a CE session is live must not fire a real
    email. `@require_POST` returns 405 on GET, and this view is not
    csrf_exempt anywhere in the route chain, so CsrfViewMiddleware applies.
    """
    future_course_id = request.POST.get('future_course_id')
    reviewer_id = request.POST.get('reviewer_id')

    if not future_course_id or not reviewer_id:
        return JsonResponse({
            'status': 'error',
            'action': 'display',
            'message': 'Missing required parameters.'
        }, status=400)

    success, message = FutureCourse.send_review_reminder(
        future_course_id, reviewer_id)

    return JsonResponse({
        'status': 'success' if success else 'error',
        'action': 'display',
        'title': 'Email Sent' if success else 'Error',
        'message': message
    })


def bulk_actions(request):
    """Handle bulk actions for future courses"""
    action = request.GET.get('action')

    if action == 'mark_as_reviewed':
        return mark_as_reviewed(request)

    if action == 'mark_as_submitted':
        return mark_as_submitted(request)

    if action == 'mark_as_pending_review':
        return mark_as_pending_review(request)

    # Default response for unknown actions
    return JsonResponse({
        'status': 'error',
        'title': 'Error',
        'message': 'Unknown action',
        'action': 'display'
    })


def mark_as_pending_review(request):
    """Open a review round on each selected request.

    Only `submitted` requests are eligible: re-selecting an already
    `pending_review` or `reviewed` request would open a new round on top
    of a live or finished one, orphaning its decisions into indistinguishable
    history (or silently un-reviewing it). Those are skipped and named in
    the response, distinctly from courses with no qualifying reviewer.
    """
    from ..review.helpers import NoReviewersError, open_review_round, review_required

    if not review_required():
        return JsonResponse({
            'status': 'warning', 'title': 'Review Disabled',
            'message': 'Review is not enabled for this tenant.',
            'action': 'display'})

    ids = request.GET.getlist('ids[]')
    if not ids:
        return JsonResponse({
            'status': 'warning', 'title': 'No Selection',
            'message': 'Please select at least one record.',
            'action': 'display'})

    marked, no_reviewer, already_open = 0, [], []
    for fc in FutureCourse.objects.filter(id__in=ids):
        label = str(fc.teacher_course.course.title
                    if fc.teacher_course else fc.id)
        if fc.status != 'submitted':
            already_open.append(label)
            continue
        try:
            open_review_round(fc)
            marked += 1
        except NoReviewersError:
            no_reviewer.append(label)

    message = f'Marked {marked} request(s) as pending review.'
    if no_reviewer:
        message += (' Skipped, no reviewer assigned to the course: '
                    + ', '.join(no_reviewer) + '.')
    if already_open:
        message += (' Skipped, already pending review or reviewed: '
                    + ', '.join(already_open) + '.')
    return JsonResponse({
        'status': 'warning' if (no_reviewer or already_open) else 'success',
        'title': 'Pending Review',
        'message': message,
        'action': 'display'})


def mark_as_reviewed(request):
    """Mark selected future courses as reviewed.

    A request that is live in `pending_review` is refused rather than
    force-closed: a bare status update would strand any undecided
    reviewer's row (still `decision=''`, forever) and drop the request off
    their Pending tab and the CE pending filter with no route to finish.
    Reset (back to `submitted`) is the designed way out of a live round;
    silently closing one here is the ambiguous behaviour we don't want.
    """
    ids = request.GET.getlist('ids[]')

    if not ids:
        return JsonResponse({
            'status': 'warning',
            'title': 'No Selection',
            'message': 'Please select at least one record.',
            'action': 'display'
        })

    courses = list(FutureCourse.objects.filter(id__in=ids))
    live = [fc for fc in courses if fc.status == 'pending_review']
    eligible_ids = [fc.id for fc in courses if fc.status != 'pending_review']

    updated_count = 0
    if eligible_ids:
        updated_count = FutureCourse.objects.filter(
            id__in=eligible_ids
        ).update(status='reviewed')

    message = f'Successfully marked {updated_count} request(s) as reviewed.'
    if live:
        labels = [str(fc.teacher_course.course.title
                      if fc.teacher_course else fc.id) for fc in live]
        message += (' Skipped, still pending review (reset to finish '
                    'or wait for all reviewers): ' + ', '.join(labels) + '.')

    return JsonResponse({
        'status': 'warning' if live else 'success',
        'title': 'Success',
        'message': message,
        'action': 'display'
    })


def mark_as_submitted(request):
    """Mark selected future courses as submitted (reset status).

    Routed through `reset_review` so the reset semantics -- clearing status
    but leaving prior-round review rows as history -- live in one place.
    """
    from ..review.helpers import reset_review

    ids = request.GET.getlist('ids[]')

    if not ids:
        return JsonResponse({
            'status': 'warning',
            'title': 'No Selection',
            'message': 'Please select at least one record.',
            'action': 'display'
        })

    updated_count = 0
    for fc in FutureCourse.objects.filter(id__in=ids):
        reset_review(fc)
        updated_count += 1

    return JsonResponse({
        'status': 'success',
        'title': 'Success',
        'message': f'Successfully marked {updated_count} request(s) as submitted.',
        'action': 'display'
    })
