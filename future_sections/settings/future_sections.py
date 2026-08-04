import datetime

from django import forms
from django.core.exceptions import ValidationError

from django.conf import settings
from django.http import JsonResponse
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.shortcuts import (
    render
)

from django.template.loader import get_template, render_to_string
from django.template import Context, Template
from django.shortcuts import render, get_object_or_404

from cis.models.term import AcademicYear, Term
from cis.models.course import Course, CourseAdministrator
from cis.models.teacher import TeacherCourseCertificate
from cis.models.section import ClassSection
from cis.models.highschool_administrator import HSPosition

try:
    from instructor_app.instructor_app.models import TeacherApplication
except ImportError:
    from instructor_app.models import TeacherApplication

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
        js = (
            'future_sections/js/settings.js',
        )

    key = "cis_future_sections"

    # ── General Settings ─────────────────────────────────────────────────
    general_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">General Settings</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

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

    academic_year = forms.ModelChoiceField(
        queryset=None,
        label="Requesting Information For",
        help_text='Select the academic year you are collecting section request information for',
        required=True
    )

    previous_academic_year = forms.ModelChoiceField(
        queryset=None,
        label="Previous Year Reference",
        help_text='Select a prior academic year to show what was previously offered at the high school',
        required=True
    )

    prev_year_class_status = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        choices=ClassSection.CLASS_STATUS,
        label="Previous Year Class Status",
        help_text='Only previous-year classes with the selected status(es) are counted in the '
                  '"Previous Year" column. Leave every option unselected to count classes of any status.',
        required=False
    )

    cycle_terms = forms.ModelMultipleChoiceField(
        queryset=Term.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label='Cycle Terms',
        help_text='Terms this cycle is collecting forecasts for. Scoped to the '
                  '"Requesting Information For" academic year selected above — only '
                  'that year\'s terms are shown. Schools that run once per AY pick '
                  'all terms in the AY; schools that run per semester pick one term '
                  'and re-open the cycle for the next.',
    )

    lookback_terms = forms.ModelMultipleChoiceField(
        queryset=Term.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Lookback Terms',
        help_text='Terms used to determine which teachers are expected to '
                  'respond (teachers who taught an Active ClassSection in any of '
                  'these terms). Scoped to the "Previous Year Reference" academic '
                  'year selected above — only that year\'s terms are shown.',
    )

    term_mapping = forms.CharField(
        max_length=2000,
        required=False,
        label="Term Mapping",
        widget=forms.HiddenInput(),
        initial='{}',
    )

    starting_date = forms.DateField()
    ending_date = forms.DateField()

    course_display_template = forms.CharField(
        max_length=500,
        required=False,
        label="Course Column Display Template",
        help_text='Template for the Course column in the requests table. '
                  'Available placeholders: {course_name}, {course_title}, '
                  '{credit_hours}, {campus_name}, {campus_code}. '
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

    require_personnel_confirmation = forms.ChoiceField(
        choices=YES_NO_SELECT_OPTIONS,
        label='Require School Personnel Confirmation?',
        help_text='If enabled, high school administrators will be asked to review and confirm their school personnel during the section request process.'
    )

    school_admin_roles = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label='High School Roles to Verify',
        help_text='Select the roles you want them to verify, confirm',
        widget=forms.CheckboxSelectMultiple
    )

    # Required only when require_personnel_confirmation is 'Yes' — enforced in
    # clean(). The settings JS hides this field whenever confirmation is off,
    # so a field-level required=True would block saving on an invisible field.
    confirm_new_personnel = forms.CharField(
        max_length=None,
        required=False,
        widget=forms.Textarea,
        label="School Personnel Confirmation Checkbox Text",
        validators=[validate_html_short_code],
        help_text='Text for the checkbox the HS admin must check to confirm they have reviewed and updated their school personnel list.'
    )

    require_all_roles_confirmed = forms.ChoiceField(
        choices=YES_NO_SELECT_OPTIONS,
        label='Require All Roles Confirmed Before Submission',
        help_text='If set to Yes, the HS admin must confirm all selected roles before they can submit. They will not be able to proceed without verifying every role.',
        required=False
    )

    require_all_teachers_confirmed = forms.ChoiceField(
        choices=YES_NO_SELECT_OPTIONS,
        label='Require All Teachers Confirmed Before Submission',
        help_text='If set to Yes, the HS admin must indicate course information for every teacher before they can submit. They will not be able to proceed without responding for all teachers.',
        required=False
    )

    confirm_administrators = forms.CharField(
        max_length=None,
        required=False,
        widget=forms.Textarea,
        label="Course Offerings Confirmation Checkbox Text",
        validators=[validate_html_short_code],
        help_text='Text for the checkbox the HS admin must check to confirm they have completed reviewing course offerings and section requests.'
    )

    confirm_administrators_header = forms.CharField(
        max_length=None,
        widget=forms.Textarea,
        label="Confirmation Section Header",
        validators=[validate_html_short_code],
        help_text='Header text displayed above the "Confirm & Continue" checkboxes on both the Course Requests and School Personnel tabs. This is shown on both tabs regardless of the personnel confirmation setting.'
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
        label="Eligible Course Status",
        help_text='Only courses with the selected status(es) will be available for section requests. For example, select "Active" to limit requests to currently active courses.',
        required=True
    )

    teacher_course_status = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        choices=TeacherCourseCertificate.STATUS_OPTIONS,
        label="Eligible Instructor Course Status",
        help_text='Only instructor-course assignments with the selected status(es) will appear in section requests. For example, select "Teaching" to only show instructors actively approved to teach a course.',
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

    enter_course_details_label = forms.CharField(
        max_length=None,
        required=False,
        initial='Enter Course Details',
        label="'Enter Course Details' Button Label",
        help_text='Wording of the button an instructor or high school administrator clicks to '
                  'record the sections they plan to offer. Leave blank to use the default.'
    )

    not_teaching_label = forms.CharField(
        max_length=None,
        required=False,
        initial='We are not teaching this course',
        label="'Not Teaching' Button Label",
        help_text='Wording of the button used to indicate a course will not be offered. '
                  'Leave blank to use the default.'
    )

    create_new_instructor_app = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        choices=TeacherCourseCertificate.STATUS_OPTIONS,
        label="Create New Instructor App For",
        required=False
    )

    default_instructor_app_status = forms.ChoiceField(
        choices=TeacherApplication.STATUS_OPTIONS,
        label="Default Status of Instructor Apps",
        help_text='Select the default status assigned to new instructor applications created during the section request process.',
        required=False
    )

    # ── Section Request Review ───────────────────────────────────────────
    review_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">Section Request Review</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    require_review = forms.ChoiceField(
        choices=YES_NO_SELECT_OPTIONS,
        label='Do course proposals need to be reviewed?',
        help_text='If enabled, designated CourseAdministrators may review and '
                  'approve (or reject) submitted section requests.',
    )

    reviewer_roles = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        choices=CourseAdministrator.ROLE_OPTIONS,
        required=False,
        label='Reviewer Roles',
        help_text='Which CourseAdministrator role(s) on the course are allowed '
                  'to review section requests.',
    )

    assign_mentor = forms.ChoiceField(
        choices=YES_NO_SELECT_OPTIONS,
        required=False,
        label='Assign a mentor during review?',
        help_text='If enabled, an approval must include a mentor (selected from '
                  'existing CourseAdministrators on the course, or created new). '
                  'Only applies when review is required.',
    )

    mentor_default_role = forms.ChoiceField(
        choices=[('', '---------')] + list(CourseAdministrator.ROLE_OPTIONS),
        required=False,
        label='Mentor CourseAdministrator Role',
        help_text='When a mentor is assigned, this is the role used on their '
                  'CourseAdministrator row for the course.',
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

    # ── Instruction Modes ─────────────────────────────────────────────────
    instruction_modes_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">Instruction Modes</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    instruction_modes = forms.CharField(
        max_length=500,
        required=False,
        label="Available Instruction Modes",
        help_text='Enter a pipe-delimited list of instruction modes. '
                  'Example: Traditional (face-to-face)|Hybrid (F2F &amp; Online)|Online. '
                  'These will appear as dropdown options when the Instruction Mode field is enabled.',
        initial='',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Traditional (face-to-face)|Hybrid (F2F & Online)|Online'
        })
    )

    # ── Locations ─────────────────────────────────────────────────────────
    location_options_header = FFields.ReadOnlyField(
        required=False,
        label=mark_safe('<h3 class="mt-4">Locations</h3>'),
        initial='',
        widget=FFields.LongLabelWidget(attrs={'class': 'border-0 bg-light h-100'})
    )

    location_options = forms.CharField(
        max_length=500,
        required=False,
        label="Available Locations",
        help_text='Enter a pipe-delimited list of locations. '
                  'Example: Main Campus|North High|Online. '
                  'These will appear as dropdown options when the Location field is enabled.',
        initial='',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Main Campus|North High|Online'
        })
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
        help_text='Email template for pending request reminders. Shortcodes: {{admin_first_name}}, {{admin_last_name}}, {{highschool}}, {{academic_year}}, {{pending_count}}, {{link}}, {{start_date}}, {{end_date}}. <a href="#" class="float-right" onClick="do_bulk_action(\'future_sections\', \'pending_notification_message\')" >See Preview</a>'
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

    def clean_cycle_terms(self):
        ids = self.data.getlist('cycle_terms')
        return Term.objects.filter(id__in=ids)

    def clean_lookback_terms(self):
        ids = self.data.getlist('lookback_terms')
        return Term.objects.filter(id__in=ids)

    def clean_reviewer_roles(self):
        return self.data.getlist('reviewer_roles')

    def clean(self):
        cleaned = super().clean()

        # The confirmation checkbox text is only shown — and only used — when
        # personnel confirmation is being requested.
        if cleaned.get('require_personnel_confirmation') == '1' \
                and not cleaned.get('confirm_new_personnel'):
            self.add_error('confirm_new_personnel',
                           forms.ValidationError(
                               'Enter the checkbox text shown to high school '
                               'administrators when personnel confirmation is '
                               'required.'))

        review_on = cleaned.get('require_review') == '1'
        if review_on and not cleaned.get('reviewer_roles'):
            self.add_error('reviewer_roles',
                           forms.ValidationError(
                               'Select at least one reviewer role when review is required.'))
        # assign_mentor / mentor_default_role only matter when review is on.
        if review_on and cleaned.get('assign_mentor') == '1' \
                and not cleaned.get('mentor_default_role'):
            self.add_error('mentor_default_role',
                           forms.ValidationError(
                               'Select a mentor role when mentor assignment is enabled.'))

        cycle_terms = cleaned.get('cycle_terms')
        if not cycle_terms:
            self.add_error('cycle_terms',
                           forms.ValidationError('Pick at least one term.'))
        else:
            ay_ids = set(t.academic_year_id for t in cycle_terms)
            if len(ay_ids) > 1:
                self.add_error('cycle_terms',
                               forms.ValidationError(
                                   'All selected terms must share an Academic Year.'))
            else:
                # The Cycle Terms must belong to the selected "Requesting
                # Information For" academic year (cleaned['academic_year'] is a
                # str UUID via clean_academic_year). Guard only when a valid AY
                # was provided; a missing AY already raises its own required error.
                selected_ay = cleaned.get('academic_year')
                if selected_ay and str(next(iter(ay_ids))) != str(selected_ay):
                    self.add_error('cycle_terms',
                                   forms.ValidationError(
                                       'Selected terms must belong to the chosen '
                                       '"Requesting Information For" academic year.'))
        return cleaned

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

        # Cycle Terms are scoped to the "Requesting Information For" AY and
        # Lookback Terms to the "Previous Year Reference" AY.
        #
        # On a BOUND form (POST/save) keep the full term queryset: Django's
        # ModelMultipleChoiceField.clean() rejects any submitted id not in the
        # queryset *before* clean_cycle_terms/clean_lookback_terms run, and those
        # custom cleaners + clean() are what actually enforce the rules. Narrowing
        # the queryset here would make every save fail with "not a valid choice".
        #
        # On an UNBOUND form (initial render) scope each list to its saved AY so
        # the checkbox lists stay short; the JS in settings.js re-fetches and
        # rebuilds a list whenever its AY dropdown changes.
        if self.is_bound:
            full_terms = Term.objects.all().order_by('-academic_year__name', 'code')
            self.fields['cycle_terms'].queryset = full_terms
            self.fields['lookback_terms'].queryset = full_terms
        else:
            saved = self.initial or {}
            req_ay = saved.get('academic_year')
            prev_ay = saved.get('previous_academic_year')
            self.fields['cycle_terms'].queryset = (
                Term.objects.filter(academic_year__id=req_ay).order_by('-code')
                if req_ay else Term.objects.none()
            )
            self.fields['lookback_terms'].queryset = (
                Term.objects.filter(academic_year__id=prev_ay).order_by('-code')
                if prev_ay else Term.objects.none()
            )

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
                f'<tr draggable="true" data-field="{name}">'
                '<td class="fw-grip text-center text-muted" '
                'style="cursor:move;width:32px;">'
                '<i class="fas fa-grip-vertical"></i></td>'
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
                f'<input type="number" readonly '
                f'class="form-control form-control-sm tfc-weight" '
                f'data-field="{name}" min="0" step="1">'
                '</td>'
                '</tr>'
            )

        placeholder_list = ", ".join(f"{{{n}}}" for n in schema_fields)
        field_weights_style = (
            '<style>'
            'table.field-weights-table tr[draggable] { cursor: grab; }'
            'table.field-weights-table td.fw-grip { width: 1.5rem; }'
            'table.field-weights-table tr.fw-dragging { opacity: .4; }'
            '</style>'
        )
        teaching_config_html = (
            field_weights_style +
            '<div id="teaching-form-config-ui" class="card mb-3">'
            '<div class="card-header"><h5 class="mb-0">Teaching Form Fields</h5></div>'
            '<div class="card-body">'
            '<table class="table table-sm table-bordered field-weights-table">'
            '<thead><tr>'
            '<th style="width:32px"></th>'
            '<th>Field</th>'
            '<th class="text-center" style="width:80px">Visible</th>'
            '<th class="text-center" style="width:80px">Required</th>'
            '<th style="width:250px">Custom Label</th>'
            '<th style="width:80px">Weight</th>'
            '</tr></thead>'
            '<tbody>'
            '<tr class="table-light">'
            '<td></td>'
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
            'Drag a row by its handle to change the order fields appear in the '
            'form. The weight column updates automatically.</small>'
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
                f'<tr draggable="true" data-field="{name}">'
                '<td class="fw-grip text-center text-muted" '
                'style="cursor:move;width:32px;">'
                '<i class="fas fa-grip-vertical"></i></td>'
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
                f'<input type="number" readonly '
                f'class="form-control form-control-sm atfc-weight" '
                f'data-field="{name}" min="0" step="1">'
                '</td>'
                '</tr>'
            )

        add_teacher_config_html = (
            '<div id="add-teacher-form-config-ui" class="card mb-3">'
            '<div class="card-header"><h5 class="mb-0">Add Teacher Form Fields</h5></div>'
            '<div class="card-body">'
            '<table class="table table-sm table-bordered field-weights-table">'
            '<thead><tr>'
            '<th style="width:32px"></th>'
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
                '<td></td>'
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
            'Drag a row by its handle to change the order fields appear in the '
            'form. The weight column updates automatically.</small>'
            '</div></div>'
            f'<script src="{static("js/field_weights.js")}"></script>'
        )

        term_mapping_html = (
            '<div id="term-mapping-ui" class="card bg-light mb-3" style="display:none;">'
            '<div class="card-body">'
            '<h5>Term Mapping</h5>'
            '<p class="text-muted small">Map each previous year term to the corresponding requesting year term.</p>'
            '<table class="table table-sm table-bordered" id="term-mapping-table">'
            '<thead><tr><th>Previous Year Term</th><th>Requesting Year Term</th></tr></thead>'
            '<tbody></tbody>'
            '</table>'
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
            elif key == 'term_mapping':
                layout_fields.append(HTML(term_mapping_html))
            layout_fields.append(key)

        self.helper.layout = Layout(
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

            start_date = fs_config.get('starting_date', '')
            end_date = fs_config.get('ending_date', '')

            message = Template(message_template)
            context = Context({
                'admin_first_name': request.user.first_name,
                'admin_last_name': request.user.last_name,
                'highschool': highschool_name,
                'academic_year': academic_year_name,
                'pending_count': pending_count,
                'link': link,
                'start_date': start_date,
                'end_date': end_date,
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
        defaults = {'mode': 'test', 'testers': 'kadaji@gmail.com', 'ending_date': '12/31/2025', 'academic_year': '91f575e7-c8e2-47a3-a2f0-3cb6ca700f9c', 'course_status': ['Active'], 'email_message': '1', 'email_subject': '1', 'starting_date': '12/23/2021', 'message_replyto': 'akadajis@syr.edu', 'welcome_message': '<p class="alert alert-danger mb-5">Change me in Settings -> Classes -> Section Requests</p>\r\n<div class="alert alert-info"><h3>Future Class / Forecasting module</h3>\r\n<p class="">As we get ready to for {{academic_year}} please use the form below to let us know what sections you plan on offering.<br><br>Below is the list of instructors and what College course(s) they are approved to teach. Click on the buttons to indicate status</p>\r\n</div>', 'teaching_message': '<div class="m-3">\r\n<div class="col-12">\r\n<p class="alert alert-danger mb-5">Change me in Settings -> Classes -> Section Requests</p>\r\n<p class="alert alert-info">Use the form below to select term and number of sections you plan on offering. Click on \'Save button\' when done.</p>\r\n</div>\r\n</div>', 'confirmation_message': '<p>Dear {{admin_first_name}},</p><p>Thank you for submitting your section information for {{academic_year}} at {{highschool}}.</p><p>Here is a summary of what was submitted:</p>{{future_sections}}', 'confirmation_subject': 'Section Request Confirmation - {{academic_year}}', 'not_teaching_message': '1', 'teacher_course_status': ['Teaching'], 'window_closed_message': 'window closed', 'previous_academic_year': 'f397c20b-c174-47e1-9d36-6e6895d5aea4', 'send_reviewed_notification': 'No', 'reviewed_email_subject': 'Your Section Request Has Been Reviewed', 'reviewed_email_message': '<p>Dear {{instructor_first_name}},</p><p>Your section request for {{course}} at {{highschool}} has been reviewed.</p>', 'pending_notification_dates': '', 'pending_notification_cron': '0 8 * * *', 'pending_notification_roles': [], 'pending_notification_subject': 'Reminder: Section Request Response Needed', 'pending_notification_message': '<p>Dear {{admin_first_name}},</p><p>This is a reminder that {{highschool}} has {{pending_count}} course(s) awaiting a response for {{academic_year}}.</p><p>Please visit the section requests page to submit your responses: {{link}}</p>', 'page_name': 'Future Section Requests', 'tab_course_requests': 'Course Requests', 'tab_school_personnel': 'School Personnel', 'course_display_template': '{course_title}', 'require_review': 'Yes', 'reviewer_roles': ['Faculty', 'Dept. Chair', 'Dean'], 'assign_mentor': 'Yes', 'mentor_default_role': 'Faculty', 'cycle_terms': [], 'lookback_terms': []}

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

    def _derive_academic_year_from_cycle_terms(self):
        """Return the AcademicYear instance shared by all cycle_terms,
        or None if cycle_terms is missing/empty."""
        cycle_terms = self.cleaned_data.get('cycle_terms')
        if not cycle_terms:
            return None
        # clean_cycle_terms already enforced single-AY; pick from the first.
        first = cycle_terms.first() if hasattr(cycle_terms, 'first') else cycle_terms[0]
        return first.academic_year if first else None

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
            # Serialize Term/QuerySet values as list-of-UUID-strings
            if key in ('cycle_terms', 'lookback_terms'):
                result[key] = [str(t.id) for t in value] if value else []
            else:
                result[key] = value

        # Derive academic_year from cycle_terms so legacy queries keep working.
        derived_ay = self._derive_academic_year_from_cycle_terms()
        if derived_ay:
            result['academic_year'] = str(derived_ay.id)
        return result