import datetime

from django import forms
from django.core.exceptions import ValidationError

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.shortcuts import (
    render
)

from django.template.loader import get_template, render_to_string
from django.template import Context, Template
from django.shortcuts import render, get_object_or_404

from cis.models.term import AcademicYear, Term
from cis.models.course import Course
from cis.models.teacher import TeacherCourseCertificate
from cis.models.highschool_administrator import HSPosition
from cis.models.crontab import CronTab

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML

from cis.validators import validate_json, validate_cron

from form_fields import fields as FFields

from cis.models.settings import Setting
from cis.validators import validate_email_list, validate_html_short_code
from cis.utils import YES_NO_SELECT_OPTIONS

from django.utils.safestring import mark_safe

from ..schemas import TeachingSectionFieldSchema

class future_sections(forms.Form):

    class Media:
        js = ('future_sections/js/settings.js',)

    key = "cis_future_sections"

    # ── General Settings ─────────────────────────────────────────────────
    general_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">General Settings</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    academic_year = forms.ModelChoiceField(
        queryset=None,
        label="Academic Year",
        help_text='Year for which the information is being requested',
        required=True
    )

    previous_academic_year = forms.ModelChoiceField(
        queryset=None,
        label="Previous Academic Year",
        help_text='This can be used to show what was offered at the high school in the past',
        required=True
    )

    starting_date = forms.DateField()
    ending_date = forms.DateField()

    page_name = forms.CharField(
        max_length=200,
        required=False,
        label="Page Name",
        help_text='Name displayed in the breadcrumb and page title (default: "Future Section Requests").',
        initial='Future Section Requests',
    )

    tab_course_requests = forms.CharField(
        max_length=200,
        required=False,
        label="Course Requests Tab Title",
        help_text='Label for the Course Requests tab (default: "Course Requests").',
        initial='Course Requests',
    )

    tab_school_personnel = forms.CharField(
        max_length=200,
        required=False,
        label="School Personnel Tab Title",
        help_text='Label for the School Personnel tab (default: "School Personnel").',
        initial='School Personnel',
    )

    course_display_template = forms.CharField(
        max_length=500,
        required=False,
        label="Course Column Display Template",
        help_text='Template for the Course column in the requests table. '
                  'Available placeholders: {course_name}, {course_title}, {credit_hours}. '
                  'Default: "{course_title}".',
        initial='{course_title}',
    )

    # ── Portal Messages ──────────────────────────────────────────────────
    messages_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">Portal Messages</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    welcome_message = forms.CharField(
        max_length=None,
        widget=forms.Textarea,
        label="Welcome Message",
        validators=[validate_html_short_code],
        help_text='This is displayed in the page where the information is filled. Customize with {{academic_year}}, {{previous_academic_year}}, {{start_date}}, {{end_date}}, {{previous_year_classes}}.'
    )

    welcome_message_personnel = forms.CharField(
        max_length=None,
        widget=forms.Textarea,
        label="Welcome Message - School Personnel Review Tab",
        validators=[validate_html_short_code],
        help_text='This is displayed in the page where the information is filled'
    )

    window_closed_message = forms.CharField(
        max_length=None,
        widget=forms.Textarea,
        label="Window Closed Message",
        help_text='This is displayed in the page when the window is closed.'
    )

    teaching_message = forms.CharField(
        max_length=None,
        widget=forms.Textarea,
        label="Message in 'Teaching' Page",
        help_text='This is displayed in the page where the section information is filled.'
    )

    new_teacher_message = forms.CharField(
        max_length=None,
        widget=forms.Textarea,
        label="Message in 'Add New Teacher' Page",
        help_text='This is displayed in the page where the section information is filled.'
    )

    edit_role_message = forms.CharField(
        max_length=None,
        widget=forms.Textarea,
        label="Message in 'Edit Role' Page",
        help_text='This is displayed in the page where the school admin info is filled.'
    )

    # ── School Personnel ─────────────────────────────────────────────────
    personnel_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">School Personnel</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    school_admin_roles = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label='High School Roles to Verify',
        help_text='Select the roles you want them to verify, confirm',
        widget=forms.CheckboxSelectMultiple
    )

    confirm_new_personnel = forms.CharField(
        max_length=None,
        widget=forms.Textarea,
        label="Checkbox Language for Adding Confirming School Personnel / Course Offerings",
        validators=[validate_html_short_code],
        help_text='This is the text for the checkbox which they have to confirm to add new school administrator and teacher.'
    )

    confirm_administrators = forms.CharField(
        max_length=None,
        required=False,
        widget=forms.Textarea,
        label="Checkbox Language for Confirming School Personnel / Course Offerings",
        validators=[validate_html_short_code],
        help_text='This is the text for the checkbox which they have to confirm saying they have completed the school personnel and course offering review.'
    )

    confirm_administrators_header = forms.CharField(
        max_length=None,
        widget=forms.Textarea,
        label="Confirm School Personnel / Course Offerings",
        validators=[validate_html_short_code],
        help_text='This is displayed before the Confirm and Continue boxes.'
    )

    # ── Course & Instructor Configuration ────────────────────────────────
    course_config_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">Course &amp; Instructor Configuration</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    course_status = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        choices=Course.STATUS_OPTIONS,
        label="Course Status",
        required=True
    )

    teacher_course_status = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        choices=TeacherCourseCertificate.STATUS_OPTIONS,
        label="Instructor Course Status",
        required=True
    )

    allow_new_teacher_create = forms.ChoiceField(
        choices=YES_NO_SELECT_OPTIONS,
        label='Allow HS Administrators to create new teachers?',
        help_text='This will create teacher with an applicant status for the course. If you select \'Yes\' make sure to also select \'Applicant\' in the teacher course status.'
    )

    new_teacher_create_label = forms.CharField(
        max_length=None,
        label="'Add New Teacher' Prompt",
        help_text='If Allowed to create new teacher, this is displayed in the page above the button to create new teacher'
    )

    create_new_instructor_app = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        choices=TeacherCourseCertificate.STATUS_OPTIONS,
        label="Create New Instructor App For",
        required=False
    )

    # ── Form Configuration ───────────────────────────────────────────────
    form_config_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">Form Configuration</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    # Legacy field - replaced by teaching_form_config.labels and teaching_form_config.help_texts
    form_field_messages = forms.CharField(
        max_length=None,
        required=False,
        initial='{}',
        validators=[validate_json],
        widget=forms.HiddenInput(),
        label="Teaching Form Field Labels (Legacy)")

    teaching_form_config = forms.CharField(
        max_length=None,
        required=False,
        validators=[validate_json],
        widget=forms.HiddenInput(),
        label="Teaching Form Configuration",
    )

    add_teacher_form_config = forms.CharField(
        max_length=None,
        required=False,
        validators=[validate_json],
        widget=forms.HiddenInput(),
        label="Add Teacher Form Configuration",
    )

    # ── Reviewed Status Email ────────────────────────────────────────────
    reviewed_email_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">Reviewed Status Email</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    send_reviewed_notification = forms.ChoiceField(
        choices=YES_NO_SELECT_OPTIONS,
        label='Send Email When Status Changes to Reviewed',
        help_text='Enable to send an email notification to the instructor and submitter when their section request is marked as reviewed.'
    )

    reviewed_email_subject = forms.CharField(
        max_length=200,
        required=False,
        label='Reviewed Notification Email Subject',
        help_text='Subject line for the email sent when status changes to reviewed.'
    )

    reviewed_email_message = forms.CharField(
        max_length=None,
        required=False,
        widget=forms.Textarea,
        validators=[validate_html_short_code],
        label='Reviewed Notification Email Message',
        help_text='Email template sent when status changes to reviewed. Shortcodes: {{course}}, {{highschool}}, {{instructor_first_name}}, {{instructor_last_name}}. <a href="#" class="float-right" onClick="do_bulk_action(\'future_sections\', \'reviewed_email_message\')" >See Preview</a>'
    )

    # ── Pending Request Notifications ────────────────────────────────────
    pending_email_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">Pending Request Notifications</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    pending_notification_dates = forms.CharField(
        required=False,
        help_text='Select specific dates to send notifications to contacts who have not responded',
        label="Pending Request Notification Dates",
        widget=forms.TextInput(attrs={
            'class': 'form-control pending-notification-dates-picker',
            'placeholder': 'Click to select dates',
            'readonly': 'readonly'
        })
    )

    pending_notification_cron = forms.CharField(
        max_length=20,
        required=False,
        help_text='Min Hr Day Month WeekDay (e.g., "0 8 * * *" for 8:00 AM)',
        label="Notification Time (Cron Expression)",
        validators=[validate_cron]
    )

    pending_notification_roles = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label='Pending Request Notification Roles',
        help_text='Select which high school administrator roles should receive pending request notifications. If none selected, all active administrators will be notified.',
        widget=forms.CheckboxSelectMultiple
    )

    pending_notification_subject = forms.CharField(
        max_length=200,
        required=False,
        label='Pending Request Notification Subject',
        help_text='Subject line for the reminder email.'
    )

    pending_notification_message = forms.CharField(
        max_length=None,
        required=False,
        widget=forms.Textarea,
        validators=[validate_html_short_code],
        label='Pending Request Notification Message',
        help_text='Email template for pending request reminders. Shortcodes: {{admin_first_name}}, {{admin_last_name}}, {{highschool}}, {{academic_year}}, {{pending_count}}, {{link}}. <a href="#" class="float-right" onClick="do_bulk_action(\'future_sections\', \'pending_notification_message\')" >See Preview</a>'
    )

    # ── Confirmation Email (sent to HS Admin after submission) ───────────
    confirmation_email_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">Confirmation Email</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    confirmation_subject = forms.CharField(
        max_length=500,
        required=False,
        label='Confirmation Email Subject',
        help_text='Subject line for the confirmation email sent to school administrators after submitting section information. Shortcodes: {{academic_year}}'
    )
    confirmation_message = forms.CharField(
        max_length=None,
        required=False,
        widget=forms.Textarea,
        validators=[validate_html_short_code],
        label='Confirmation Email Message',
        help_text='Email template sent to school administrators after they submit information. Shortcodes: {{future_sections}}, {{academic_year}}, {{admin_first_name}}, {{admin_last_name}}, {{highschool}}. <a href="#" class="float-right" onClick="do_bulk_action(\'future_sections\', \'confirmation_message\')" >See Preview</a>'
    )

    def clean_teacher_course_status(self):
        if self.data.get('allow_new_teacher_create') == '1' and 'Applicant' not in self.data.getlist('teacher_course_status'):
            raise ValidationError('Please select \'Applicant\' from the list ')
        return self.data.getlist('teacher_course_status')
        
    def clean_starting_date(self):
        data = self.cleaned_data['starting_date']
        return data.strftime('%m/%d/%Y')

    def clean_academic_year(self):
        return str(self.cleaned_data.get('academic_year').id)
    
    def clean_school_admin_roles(self):
        return self.data.getlist('school_admin_roles')

    def clean_pending_notification_roles(self):
        return self.data.getlist('pending_notification_roles')

    def clean_previous_academic_year(self):
        data = self.cleaned_data.get('previous_academic_year')

        # if str(data.id) == self.cleaned_data.get('academic_year'):
        #     raise ValidationError('Requesting academic year and previous academic year cannot be the same')

        return str(self.cleaned_data.get('previous_academic_year').id)

    def clean_ending_date(self):
        data = self.cleaned_data['ending_date'].strftime('%m/%d/%Y')

        data = datetime.datetime.strptime(data, '%m/%d/%Y')
        starting_date = datetime.datetime.strptime(
            self.cleaned_data.get('starting_date'), '%m/%d/%Y'
        )

        if data < starting_date:
            raise ValidationError('Please enter a valid end date', code='invalid')
        
        return data.strftime('%m/%d/%Y')

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['academic_year'].queryset = AcademicYear.objects.all().order_by('-name')
        self.fields['previous_academic_year'].queryset = AcademicYear.objects.all().order_by('-name')

        self.fields['school_admin_roles'].queryset = HSPosition.objects.all().order_by('name')
        self.fields['pending_notification_roles'].queryset = HSPosition.objects.all().order_by('name')

        # self.fields['term'].queryset = Term.objects.all().order_by('-code')

        self.request = request
        self.helper = FormHelper()
        self.helper.attrs = {'target':'_blank'}
        self.helper.form_method = 'POST'
        self.helper.form_action = reverse_lazy(
            'setting:run_record', args=[request.GET.get('report_id')])
        self.helper.add_input(Submit('submit', 'Save Setting'))

        # Build teaching form config visual UI
        schema_fields = TeachingSectionFieldSchema.get_available_field_names()
        rows_html = ""
        for name in schema_fields:
            meta = TeachingSectionFieldSchema.get_field_meta(name)
            default_label = meta.get("default_label", name)
            rows_html += (
                '<tr>'
                f'<td>{default_label}</td>'
                '<td class="text-center">'
                f'<input type="checkbox" class="tfc-visible" data-field="{name}">'
                '</td>'
                '<td class="text-center">'
                f'<input type="checkbox" class="tfc-required" data-field="{name}">'
                '</td>'
                '<td>'
                f'<input type="text" class="form-control form-control-sm tfc-label" '
                f'data-field="{name}" placeholder="{default_label}">'
                '</td>'
                '<td>'
                f'<input type="number" class="form-control form-control-sm tfc-weight" '
                f'data-field="{name}" min="0" step="1">'
                '</td>'
                '</tr>'
            )

        placeholder_list = ", ".join(f"{{{n}}}" for n in schema_fields)
        teaching_config_html = (
            '<div id="teaching-form-config-ui" class="card mb-3">'
            '<div class="card-header"><h5 class="mb-0">Teaching Form Fields</h5></div>'
            '<div class="card-body">'
            '<table class="table table-sm table-bordered">'
            '<thead><tr>'
            '<th>Field</th>'
            '<th class="text-center" style="width:80px">Visible</th>'
            '<th class="text-center" style="width:80px">Required</th>'
            '<th style="width:250px">Custom Label</th>'
            '<th style="width:80px">Weight</th>'
            '</tr></thead>'
            '<tbody>'
            '<tr class="table-light">'
            '<td>Term <span class="badge badge-secondary">Always included</span></td>'
            '<td class="text-center"><input type="checkbox" checked disabled></td>'
            '<td class="text-center"><input type="checkbox" checked disabled></td>'
            '<td><input type="text" class="form-control form-control-sm" disabled '
            'placeholder="Term"></td>'
            '<td><input type="number" class="form-control form-control-sm" disabled '
            'value="0"></td>'
            '</tr>'
        )
        teaching_config_html += rows_html
        teaching_config_html += (
            '</tbody></table>'
            '<small class="form-text text-muted mb-3 d-block">'
            'Lighter weighted fields appear at the top of the form.</small>'
            '<div class="form-group mt-3">'
            '<div class="custom-control custom-checkbox">'
            '<input type="checkbox" class="custom-control-input" id="tfc-show-syllabus">'
            '<label class="custom-control-label" for="tfc-show-syllabus">'
            'Show Syllabus Upload</label>'
            '</div></div>'
            '<div class="form-group mt-3">'
            '<label for="tfc-display-template">Display Template</label>'
            '<textarea id="tfc-display-template" class="form-control" rows="2">'
            '</textarea>'
            '<small class="form-text text-muted">Placeholders: {term_name}, '
        )
        teaching_config_html += placeholder_list
        teaching_config_html += (
            ', {syllabus_link}</small>'
            '</div>'
            '</div></div>'
        )

        # Build add teacher form config visual UI
        # Only the new-teacher fields are configurable; the rest are always included
        add_teacher_fields = [
            ('teacher_first_name', 'Teacher First Name'),
            ('teacher_last_name', 'Teacher Last Name'),
            ('teacher_email', 'Teacher Email'),
        ]
        always_included = [
            ('highschool', 'School'),
            ('course', 'Course'),
            ('term', 'Term'),
            ('teacher', 'Teacher'),
        ]

        at_rows_html = ""
        for name, default_label in add_teacher_fields:
            at_rows_html += (
                '<tr>'
                f'<td>{default_label}</td>'
                '<td class="text-center">'
                f'<input type="checkbox" class="atfc-visible" data-field="{name}">'
                '</td>'
                '<td class="text-center">'
                f'<input type="checkbox" class="atfc-required" data-field="{name}">'
                '</td>'
                '<td>'
                f'<input type="text" class="form-control form-control-sm atfc-label" '
                f'data-field="{name}" placeholder="{default_label}">'
                '</td>'
                '<td>'
                f'<input type="number" class="form-control form-control-sm atfc-weight" '
                f'data-field="{name}" min="0" step="1">'
                '</td>'
                '</tr>'
            )

        add_teacher_config_html = (
            '<div id="add-teacher-form-config-ui" class="card mb-3">'
            '<div class="card-header"><h5 class="mb-0">Add Teacher Form Fields</h5></div>'
            '<div class="card-body">'
            '<table class="table table-sm table-bordered">'
            '<thead><tr>'
            '<th>Field</th>'
            '<th class="text-center" style="width:80px">Visible</th>'
            '<th class="text-center" style="width:80px">Required</th>'
            '<th style="width:250px">Custom Label</th>'
            '<th style="width:80px">Weight</th>'
            '</tr></thead>'
            '<tbody>'
        )
        for name, default_label in always_included:
            add_teacher_config_html += (
                '<tr class="table-light">'
                f'<td>{default_label} <span class="badge badge-secondary">Always included</span></td>'
                '<td class="text-center"><input type="checkbox" checked disabled></td>'
                '<td class="text-center"><input type="checkbox" checked disabled></td>'
                f'<td><input type="text" class="form-control form-control-sm" disabled '
                f'placeholder="{default_label}"></td>'
                '<td><input type="number" class="form-control form-control-sm" disabled '
                'value="0"></td>'
                '</tr>'
            )
        add_teacher_config_html += at_rows_html
        add_teacher_config_html += (
            '</tbody></table>'
            '<small class="form-text text-muted mb-3 d-block">'
            'Lighter weighted fields appear at the top of the form.</small>'
            '</div></div>'
        )

        # Build layout with config UIs inserted before their hidden fields
        field_keys = list(self.fields.keys())
        layout_fields = []
        for key in field_keys:
            if key == 'teaching_form_config':
                layout_fields.append(HTML(teaching_config_html))
            elif key == 'add_teacher_form_config':
                layout_fields.append(HTML(add_teacher_config_html))
            layout_fields.append(key)

        self.helper.layout = Layout(
            HTML('<script src="/static/future_sections/js/settings.js"></script>'),
            *layout_fields
        )

    def preview(self, request, field_name):
        from django.utils.safestring import mark_safe
        from ..models import FutureCourse
        from cis.models.term import AcademicYear

        fs_config = future_sections.from_db()

        if field_name == 'confirmation_message':
            subject_template = fs_config.get('confirmation_subject', '')
            message_template = fs_config.get('confirmation_message', '')

            # Try to find a random FutureCourse with section data for realistic preview
            academic_year_id = fs_config.get('academic_year')
            sample_fc = FutureCourse.objects.filter(
                academic_year__id=academic_year_id,
                section_info__teaching='yes'
            ).select_related(
                'teacher_course__course',
                'teacher_course__teacher_highschool__highschool',
                'teacher_course__teacher_highschool__teacher__user',
            ).order_by('?').first()

            if sample_fc:
                highschool = sample_fc.teacher_course.teacher_highschool.highschool

                # Get all FutureCourses for this highschool to build a realistic list
                future_courses = FutureCourse.objects.filter(
                    academic_year__id=academic_year_id,
                    teacher_course__teacher_highschool__highschool=highschool
                ).select_related(
                    'teacher_course__course',
                    'teacher_course__teacher_highschool__highschool',
                    'teacher_course__teacher_highschool__teacher__user',
                )

                from ..views.api import FutureSectionsActionViewSet
                future_sections_text = FutureSectionsActionViewSet._build_future_sections_table(future_courses)
                highschool_name = highschool.name
                academic_year_name = str(sample_fc.academic_year)
            else:
                # Fallback sample table when no data exists
                future_sections_text = (
                    "<table style='border-collapse:collapse;width:100%;'>"
                    "<tr>"
                    "<th style='padding:6px;border:1px solid #ddd;text-align:left;background:#f5f5f5;'>Course</th>"
                    "<th style='padding:6px;border:1px solid #ddd;text-align:left;background:#f5f5f5;'>High School</th>"
                    "<th style='padding:6px;border:1px solid #ddd;text-align:left;background:#f5f5f5;'>Instructor</th>"
                    "<th style='padding:6px;border:1px solid #ddd;text-align:left;background:#f5f5f5;'>Status</th>"
                    "<th style='padding:6px;border:1px solid #ddd;text-align:left;background:#f5f5f5;'>Details</th>"
                    "</tr>"
                    "<tr>"
                    "<td style='padding:6px;border:1px solid #ddd;'>ENG 101</td>"
                    "<td style='padding:6px;border:1px solid #ddd;'>Sample High School</td>"
                    "<td style='padding:6px;border:1px solid #ddd;'>Smith, John</td>"
                    "<td style='padding:6px;border:1px solid #ddd;'>Teaching</td>"
                    "<td style='padding:6px;border:1px solid #ddd;'>Fall 2025 | Estimated Enrollment: 25</td>"
                    "</tr>"
                    "<tr>"
                    "<td style='padding:6px;border:1px solid #ddd;'>MAT 201</td>"
                    "<td style='padding:6px;border:1px solid #ddd;'>Sample High School</td>"
                    "<td style='padding:6px;border:1px solid #ddd;'>Doe, Jane</td>"
                    "<td style='padding:6px;border:1px solid #ddd;'>Not Teaching</td>"
                    "<td style='padding:6px;border:1px solid #ddd;'></td>"
                    "</tr>"
                    "</table>"
                )
                highschool_name = "Sample High School"
                academic_year_name = str(AcademicYear.objects.first()) if AcademicYear.objects.exists() else "2025-2026"

            message = Template(message_template)
            context = Context({
                'future_sections': mark_safe(future_sections_text),
                'academic_year': academic_year_name,
                'admin_first_name': request.user.first_name,
                'admin_last_name': request.user.last_name,
                'highschool': highschool_name,
            })

            text_body = message.render(context)

            return render(
                request,
                'cis/email.html',
                {
                    'message': text_body
                }
            )

        if field_name == 'pending_notification_message':
            message_template = fs_config.get('pending_notification_message', '')

            academic_year_id = fs_config.get('academic_year')
            academic_year_name = ''
            highschool_name = 'Sample High School'
            pending_count = 5

            if academic_year_id:
                try:
                    ay = AcademicYear.objects.get(id=academic_year_id)
                    academic_year_name = str(ay)
                except AcademicYear.DoesNotExist:
                    pass

                # Try to find a highschool with pending courses for realistic data
                from cis.models.teacher import TeacherCourseCertificate
                from ..models import FutureCourse

                received_ids = FutureCourse.objects.filter(
                    academic_year__id=academic_year_id
                ).values_list('teacher_course__certificate_id', flat=True)

                pending_qs = TeacherCourseCertificate.objects.filter(
                    course__status__in=fs_config.get('course_status', []),
                    status__in=fs_config.get('teacher_course_status', [])
                ).exclude(
                    certificate_id__in=received_ids
                ).select_related('teacher_highschool__highschool')

                first_pending = pending_qs.first()
                if first_pending:
                    highschool_name = first_pending.teacher_highschool.highschool.name
                    pending_count = pending_qs.filter(
                        teacher_highschool__highschool=first_pending.teacher_highschool.highschool
                    ).count()

            site_url = getattr(settings, 'SITE_URL', '')
            link = f"{site_url}/highschool_admin/future_sections/"

            message = Template(message_template)
            context = Context({
                'admin_first_name': request.user.first_name,
                'admin_last_name': request.user.last_name,
                'highschool': highschool_name,
                'academic_year': academic_year_name,
                'pending_count': pending_count,
                'link': link,
            })

            text_body = message.render(context)

            return render(
                request,
                'cis/email.html',
                {
                    'message': text_body
                }
            )

        if field_name == 'reviewed_email_message':
            message_template = fs_config.get('reviewed_email_message', '')

            from ..models import FutureCourse

            # Try to find a random FutureCourse for realistic data
            academic_year_id = fs_config.get('academic_year')
            sample_fc = FutureCourse.objects.filter(
                academic_year__id=academic_year_id
            ).select_related(
                'teacher_course__course',
                'teacher_course__teacher_highschool__highschool',
                'teacher_course__teacher_highschool__teacher__user',
            ).order_by('?').first()

            if sample_fc:
                course_name = str(sample_fc.teacher_course.course)
                highschool_name = sample_fc.teacher_course.teacher_highschool.highschool.name
                instructor_first = sample_fc.teacher_course.teacher_highschool.teacher.user.first_name
                instructor_last = sample_fc.teacher_course.teacher_highschool.teacher.user.last_name
            else:
                course_name = 'ENG 101'
                highschool_name = 'Sample High School'
                instructor_first = 'John'
                instructor_last = 'Smith'

            message = Template(message_template)
            context = Context({
                'course': course_name,
                'highschool': highschool_name,
                'instructor_first_name': instructor_first,
                'instructor_last_name': instructor_last,
            })

            text_body = message.render(context)

            return render(
                request,
                'cis/email.html',
                {
                    'message': text_body
                }
            )

    def install(self):
        defaults = {'mode': 'test', 'testers': 'kadaji@gmail.com', 'ending_date': '12/31/2025', 'academic_year': '91f575e7-c8e2-47a3-a2f0-3cb6ca700f9c', 'course_status': ['Active'], 'email_message': '1', 'email_subject': '1', 'starting_date': '12/23/2021', 'message_replyto': 'akadajis@syr.edu', 'welcome_message': '<p class="alert alert-danger mb-5">Change me in Settings -> Classes -> Section Requests</p>\r\n<div class="alert alert-info"><h3>Future Class / Forecasting module</h3>\r\n<p class="">As we get ready to for {{academic_year}} please use the form below to let us know what sections you plan on offering.<br><br>Below is the list of instructors and what College course(s) they are approved to teach. Click on the buttons to indicate status</p>\r\n</div>', 'teaching_message': '<div class="m-3">\r\n<div class="col-12">\r\n<p class="alert alert-danger mb-5">Change me in Settings -> Classes -> Section Requests</p>\r\n<p class="alert alert-info">Use the form below to select term and number of sections you plan on offering. Click on \'Save button\' when done.</p>\r\n</div>\r\n</div>', 'confirmation_message': '<p>Dear {{admin_first_name}},</p><p>Thank you for submitting your section information for {{academic_year}} at {{highschool}}.</p><p>Here is a summary of what was submitted:</p>{{future_sections}}', 'confirmation_subject': 'Section Request Confirmation - {{academic_year}}', 'not_teaching_message': '1', 'teacher_course_status': ['Teaching'], 'window_closed_message': 'window closed', 'previous_academic_year': 'f397c20b-c174-47e1-9d36-6e6895d5aea4', 'send_reviewed_notification': 'No', 'reviewed_email_subject': 'Your Section Request Has Been Reviewed', 'reviewed_email_message': '<p>Dear {{instructor_first_name}},</p><p>Your section request for {{course}} at {{highschool}} has been reviewed.</p>', 'pending_notification_dates': '', 'pending_notification_cron': '0 8 * * *', 'pending_notification_roles': [], 'pending_notification_subject': 'Reminder: Section Request Response Needed', 'pending_notification_message': '<p>Dear {{admin_first_name}},</p><p>This is a reminder that {{highschool}} has {{pending_count}} course(s) awaiting a response for {{academic_year}}.</p><p>Please visit the section requests page to submit your responses: {{link}}</p>', 'page_name': 'Future Section Requests', 'tab_course_requests': 'Course Requests', 'tab_school_personnel': 'School Personnel', 'course_display_template': '{course_title}'}

        try:
            setting = Setting.objects.get(key=self.key)
        except Setting.DoesNotExist:
            setting = Setting()
            setting.key = self.key

        setting.value = defaults
        setting.save()

    @classmethod
    def from_db(cls):
        try:
            setting = Setting.objects.get(key=cls.key)
            return setting.value
        except Setting.DoesNotExist:
            return {}

    def run_record(self):
        try:
            setting = Setting.objects.get(key=self.key)
        except Setting.DoesNotExist:
            setting = Setting()
            setting.key = self.key

        setting.value = self._to_python()
        setting.save()

        return JsonResponse({
            'message': 'Successfully saved settings',
            'status': 'success'})

    def _to_python(self):
        """
        Return dict of form elements from $_POST
        """
        # Save cron schedule to CronTab for pending notifications
        cron_expr = self.cleaned_data.get('pending_notification_cron')
        if cron_expr:
            cron, created = CronTab.objects.get_or_create(
                command='notify_pending_section_requests'
            )
            cron.cron = cron_expr
            cron.save()

        result = {}
        for key, value in self.cleaned_data.items():
            result[key] = value

        return result