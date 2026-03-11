# future_sections/models.py
"""
Future Sections models - moved from cis/models/future_sections.py

These models track instructor section projections for upcoming academic years.
"""
import uuid
import csv
import datetime

from django.conf import settings
from django.db import models
from django.db.models import JSONField
from django.utils.safestring import mark_safe
from django.core.mail import EmailMessage
from django.template import Context, Template
from django.http import HttpResponse
from django.urls import reverse

from model_utils import FieldTracker

from cis.models.settings import Setting


class FutureProjection(models.Model):
    """
    Tracks a highschool's future section projection for an academic year.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    academic_year = models.ForeignKey(
        'cis.AcademicYear', on_delete=models.PROTECT, blank=True, null=True,
        related_name='fs_futureprojection_set'
    )
    highschool = models.ForeignKey(
        'cis.HighSchool', on_delete=models.PROTECT, blank=True, null=True,
        related_name='fs_futureprojection_set'
    )
    created_by = models.ForeignKey(
        'cis.CustomUser', on_delete=models.PROTECT, blank=True, null=True,
        related_name='fs_futureprojection_set'
    )

    meta = JSONField(default=dict)
    started_on = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = (('academic_year', 'highschool'))

    @property
    def confirmed_administrators(self):
        return self.meta.get('confirmed_administrators', 'No')

    @property
    def confirmed_class_sections(self):
        return self.meta.get('confirmed_class_sections', 'No')

    @property
    def confirmed_choice_class_sections(self):
        return self.meta.get('confirmed_choice_class_sections', 'No')

    @property
    def confirmed_facilitator_class_sections(self):
        return self.meta.get('confirmed_facilitator_class_sections', 'No')


class FutureCourse(models.Model):
    """
    Future Course model - tracks an instructor's intention to teach a course.
    """
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('reviewed', 'Reviewed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    academic_year = models.ForeignKey(
        'cis.AcademicYear', on_delete=models.PROTECT, blank=True, null=True,
        related_name='fs_futurecourse_set'
    )
    teacher_course = models.ForeignKey(
        'cis.TeacherCourseCertificate', on_delete=models.CASCADE,
        blank=True, null=True,
        related_name='fs_futurecourse_set'
    )
    term = models.ForeignKey(
        'cis.Term', on_delete=models.PROTECT, blank=True, null=True,
        related_name='fs_futurecourse_set'
    )

    meta = JSONField(default=dict)

    started_on = models.DateField(auto_now=True)
    last_viewed_on = models.DateField(auto_now_add=True)
    submitted_on = models.DateField(blank=True, null=True)

    section_info = JSONField(default=dict)

    submitted_by = models.ForeignKey(
        'cis.CustomUser', on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='fs_futurecourse_submitted'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='submitted'
    )

    # Track status field changes for signal notifications
    tracker = FieldTracker(fields=['status'])

    class Meta:
        unique_together = (('teacher_course', 'academic_year'))

    def __str__(self):
        return f"{self.teacher_course.teacher_highschool.teacher} - {self.teacher_course.course} ({self.academic_year})"

    def create_teacher_application(self):
        from instructor_app.models.teacher_applicant import (
            TeacherApplicant, TeacherApplication,
            ApplicantSchoolCourse, ApplicationUpload
        )

        from future_sections import future_sections as fs_settings

        fs_config = fs_settings.from_db()
        default_status = fs_config.get('default_instructor_app_status', 'In Progress')

        teacher_app = TeacherApplication(
            user=self.teacher_course.teacher_highschool.teacher.user,
            highschool=self.teacher_course.teacher_highschool.highschool,
            status=default_status,
            createdon=datetime.datetime.now()
        )

        if not self.teacher_course.teacher_highschool.teacher.user.education_background:
            self.teacher_course.teacher_highschool.teacher.user.education_background = {}
            self.teacher_course.teacher_highschool.teacher.user.save()

        teacher_app.save()

        app_course = ApplicantSchoolCourse(
            teacherapplication=teacher_app,
            course=self.teacher_course.course,
            highschool=self.teacher_course.teacher_highschool.highschool,
            status='---',
            misc_info={},
            starting_academic_year=self.academic_year
        )
        app_course.save()

        for s_info in self.section_info.get('sections', []):
            file_path = s_info.get('file')
            if file_path:
                import requests
                from django.core.files.base import ContentFile
                from urllib.parse import urlparse
                import os

                s3_url = file_path
                response = requests.get(s3_url)

                if response.status_code == 200:
                    parsed_url = urlparse(s3_url)
                    filename = os.path.basename(parsed_url.path)

                    file_content = ContentFile(response.content)

                    app_upload = ApplicationUpload(
                        teacher_application=teacher_app
                    )
                    app_upload.save()
                    app_upload.upload.save(filename, file_content, save=True)

    @classmethod
    def get_or_add(cls, teacher_course, academic_year, section_info=None, submitter=None):
        try:
            record = FutureCourse.objects.get(
                teacher_course=teacher_course,
                academic_year=academic_year
            )
            return record
        except FutureCourse.DoesNotExist:
            if not section_info:
                section_info = {}

            # Track who submitted this future course request
            meta = {}
            if submitter:
                meta['submitted_by'] = {
                    'id': str(submitter.id),
                    'email': submitter.email,
                    'name': submitter.get_full_name()
                }

            record = FutureCourse(
                teacher_course=teacher_course,
                academic_year=academic_year,
                section_info=section_info,
                meta=meta,
                submitted_by=submitter
            )
            record.save()
            return record

    def send_confirmation_email(self, mode="text"):
        """
        Sends confirmation email to instructor
        """
        subject = FutureCourse.get_setting_value('confirmation_subject')
        message = FutureCourse.get_setting_value('confirmation_message')
        message_replyto = FutureCourse.get_setting_value('message_replyto')

        if FutureCourse.get_setting_value('mode') == 'test':
            to = FutureCourse.get_setting_value('testers').split(",")
        else:
            to = [self.teacher.user.email]

        message = message.replace(
            "{instructor_first_name}", self.teacher.user.first_name)
        message = message.replace(
            "{future_sections}", self.as_string(mode)
        )
        message = message.replace(
            "{academic_year}", self.academic_year.name)

        email = EmailMessage(
            subject,
            message,
            settings.MY_CE.get('default_from'),
            to,
            reply_to=[message_replyto]
        )
        return email.send(fail_silently=True)

    def has_completed_all_courses(self):
        """
        Return bool indicating the instructor has responded to all
        eligible course(s)
        """
        from cis.models.teacher import TeacherCourseCertificate

        ht_courses = TeacherCourseCertificate.objects.filter(
            teacher_highschool__teacher=self.teacher,
            course__status__in=FutureCourse.get_active_course_status(),
            status__in=FutureCourse.get_active_course_certificate_status()
        ).exclude(
            id__in=FutureSection.objects.filter(
                future_course=self.id
            ).values_list('teacher_course', flat=True)).all()

        return True if not ht_courses.exists() else False

    def as_string(self, mode='text'):
        """
        Return the future section information as a string.
        Uses the section_display property for consistent formatting based on settings.
        """
        result = ""

        if mode == 'text':
            # Get course/highschool prefix
            prefix = f"{self.teacher_course.course} at {self.teacher_course.teacher_highschool.highschool.name}, "

            # Check teaching status from section_info
            if self.section_info and self.section_info.get('teaching') == 'yes':
                # Use section_display property for formatted output
                displays = self.section_display
                if displays:
                    for display in displays:
                        # Strip HTML tags for text mode
                        import re
                        text_display = re.sub(r'<[^>]+>', '', display)
                        result += prefix + text_display + "\r\n"
                else:
                    result += prefix + "Teaching\r\n"
            elif self.section_info and self.section_info.get('teaching') == 'no':
                result += prefix + "Not teaching\r\n"

        return result

    @staticmethod
    def welcome_message(highschools=None):
        from .settings.future_sections import future_sections as fs_settings
        from cis.models.term import AcademicYear
        from cis.models.section import ClassSection

        fs_config = fs_settings.from_db()
        message = Template(fs_config.get('welcome_message', 'not configured'))

        academic_year = AcademicYear.objects.get(
            pk=fs_config.get('academic_year')
        )
        previous_academic_year = AcademicYear.objects.get(
            pk=fs_config.get('previous_academic_year')
        )

        class_section_html = ""
        if highschools:
            class_sections = ClassSection.objects.filter(
                highschool__in=highschools
            ).order_by('term__code')

            class_section_html = "<table class='table table-striped'><tr><th>Term</th><th>Course</th><th>Instructor</th></tr>"
            for class_section in class_sections:
                class_section_html += f"<tr><td>{class_section.term}</td><td>{class_section.course}</td><td>{class_section.teacher}</td></tr>"
            class_section_html += "</table>"

        context = Context({
            'academic_year': str(academic_year),
            'previous_academic_year': str(previous_academic_year),
            'start_date': fs_config.get('starting_date'),
            'end_date': fs_config.get('ending_date'),
            'previous_year_classes': mark_safe(class_section_html)
        })
        return message.render(context)

    @staticmethod
    def get_setting_value(setting_key):
        key = "cis_future_sections"
        try:
            setting = Setting.objects.get(key=key)
            return setting.value.get(setting_key, '')
        except Exception:
            return ""

    @staticmethod
    def is_window_open():
        from .settings.future_sections import future_sections as fs_settings

        fs_config = fs_settings.from_db()
        start_date = datetime.datetime.strptime(
            fs_config.get('starting_date', '10/10/2020'),
            "%m/%d/%Y"
        )

        end_date = datetime.datetime.strptime(
            fs_config.get('ending_date', '10/10/2020'),
            "%m/%d/%Y"
        )

        now = datetime.datetime.now()
        if now >= start_date and now <= end_date:
            return True
        return False

    @staticmethod
    def get_active_course_certificate_status():
        """
        Return the list of course certificate status for which future course should
        pull courses from
        """
        key = "cis_future_sections"
        try:
            setting = Setting.objects.get(key=key)
            return setting.value.get('teacher_course_status')
        except Setting.DoesNotExist:
            return []

    @staticmethod
    def get_active_course_status():
        """
        Return the list of course status for which future course should
        pull courses from
        """
        key = "cis_future_sections"
        try:
            setting = Setting.objects.get(key=key)
            return setting.value.get('course_status')
        except Setting.DoesNotExist:
            return []

    @staticmethod
    def get_active_academic_year():
        """
        Return the academic year for which future course form is set to
        """
        from cis.models.term import AcademicYear

        key = "cis_future_sections"
        try:
            setting = Setting.objects.get(key=key)
            return setting.value.get('academic_year')
        except Setting.DoesNotExist:
            return str(AcademicYear.objects.all()[0].id)

    @staticmethod
    def get_active_term():
        """
        Return the term for which future course form is set to
        """
        from cis.models.term import Term

        key = "cis_future_sections"
        try:
            setting = Setting.objects.get(key=key)
            return setting.value.get('term')
        except Setting.DoesNotExist:
            return str(Term.objects.all()[0].id)

    @staticmethod
    def get_instructors_missing(academic_year, course=''):
        """
        Return list of instructors who have not completed the future course
        """
        pass

    @staticmethod
    def get_link(teacher, academic_year):
        """
        Return course schedule URL
        """
        pass

    @property
    def teaching_or_not(self):
        return 'Yes' if self.section_info.get('teaching') == 'yes' else 'No'

    @property
    def section_display(self):
        """
        Generate formatted display string for section info based on settings config.
        Returns a list of display strings, one per section.
        """
        import json
        from .settings.future_sections import future_sections as fs_settings
        from .schemas import TeachingSectionFieldSchema

        fs_config = fs_settings.from_db()

        # Get teaching form configuration
        try:
            form_config = json.loads(fs_config.get('teaching_form_config', '{}'))
        except Exception:
            form_config = {}

        display_template = form_config.get(
            'display_template',
            '{term_name} | {syllabus_link} | Estimated Enrollment: {estimated_enrollment}'
        )
        show_syllabus = form_config.get('show_syllabus', True)

        sections = self.section_info.get('sections', []) if self.section_info else []
        displays = []

        for section in sections:
            displays.append(
                TeachingSectionFieldSchema.format_section_display(
                    section, display_template, show_syllabus
                )
            )

        return displays

    def additional_fields(self):
        """Return list of additional field names from teaching_form_config.

        Validates configured names against the schema so typos are silently
        dropped rather than causing downstream key errors.
        """
        import json
        from .settings.future_sections import future_sections as fs_settings
        from .schemas import TeachingSectionFieldSchema

        fs_config = fs_settings.from_db()
        try:
            form_config = json.loads(fs_config.get('teaching_form_config', '{}'))
        except (json.JSONDecodeError, TypeError):
            form_config = {}

        configured = form_config.get('fields', ['term', 'estimated_enrollment'])
        valid_names = set(TeachingSectionFieldSchema.get_available_field_names()) | {'term'}
        return [f for f in configured if f in valid_names]

    def get_by_property(self, index, key):
        """Get section property by index and key from section_info."""
        sections = self.section_info.get('sections', []) if self.section_info else []
        if index < len(sections):
            value = sections[index].get(key, '')
            # Handle term_name special case - when asking for 'term', return term_name if available
            if key == 'term' and sections[index].get('term_name'):
                return sections[index].get('term_name')
            return value if value is not None else ''
        return ''

    @classmethod
    def get_export_labels(cls):
        """Get field labels from teaching_form_config for export headers.

        Merges schema default labels with any overrides from settings so that
        exports always have a human-readable header even without explicit config.
        """
        import json
        from .settings.future_sections import future_sections as fs_settings
        from .schemas import TeachingSectionFieldSchema

        fs_config = fs_settings.from_db()
        try:
            form_config = json.loads(fs_config.get('teaching_form_config', '{}'))
        except (json.JSONDecodeError, TypeError):
            form_config = {}

        active_fields = form_config.get('fields', ['term', 'estimated_enrollment'])
        label_overrides = form_config.get('labels', {})
        return TeachingSectionFieldSchema.get_export_labels(active_fields, label_overrides)

    @classmethod
    def notify_pending_section_requests(cls, *args, **kwargs):
        """
        Send notifications to school contacts with pending section requests.

        Returns:
            tuple: (summary, detailed_log)
        """
        from django.conf import settings as django_settings
        from django.db.models import Count
        from django.template.loader import get_template
        from mailer import send_html_mail
        from cis.models.teacher import TeacherCourseCertificate
        from cis.models.highschool_administrator import HSAdministratorPosition
        from cis.models.term import AcademicYear
        from .settings.future_sections import future_sections as fs_settings

        detailed_log = {
            'emails_sent': [],
            'errors': [],
            'skipped': []
        }
        emails_sent = 0
        errors = 0

        fs_config = fs_settings.from_db()

        # Check if today is a notification date
        today = datetime.date.today().strftime('%m/%d/%Y')
        notification_dates_str = fs_config.get('pending_notification_dates', '')
        notification_dates = [d.strip() for d in notification_dates_str.split(',') if d.strip()]

        if today not in notification_dates:
            summary = f"Skipped: {today} is not a notification date"
            detailed_log['skipped'].append(summary)
            return summary, detailed_log

        academic_year_id = fs_config.get('academic_year')
        if not academic_year_id:
            summary = "Error: No academic year configured"
            detailed_log['errors'].append(summary)
            return summary, detailed_log

        # Get certificate IDs that have already submitted
        received_records = cls.objects.filter(
            academic_year__id=academic_year_id
        ).values_list('teacher_course__certificate_id', flat=True)

        # Get pending certificates grouped by high school
        pending_by_school = TeacherCourseCertificate.objects.filter(
            course__status__in=fs_config.get('course_status', []),
            status__in=fs_config.get('teacher_course_status', [])
        ).exclude(
            certificate_id__in=received_records
        ).values('teacher_highschool__highschool__id').annotate(
            pending_count=Count('id')
        )

        school_ids = [item['teacher_highschool__highschool__id'] for item in pending_by_school]
        pending_counts = {
            str(item['teacher_highschool__highschool__id']): item['pending_count']
            for item in pending_by_school
        }

        if not school_ids:
            summary = "No schools with pending section requests found"
            detailed_log['skipped'].append(summary)
            return summary, detailed_log

        # Get school admin roles to notify
        admin_roles = fs_config.get('pending_notification_roles', [])

        # Get administrators for schools with pending requests
        if admin_roles:
            admins = HSAdministratorPosition.objects.filter(
                highschool__id__in=school_ids,
                position__id__in=admin_roles,
                status='active'
            ).select_related('hsadmin__user', 'highschool')
        else:
            # If no roles specified, get all active admins
            admins = HSAdministratorPosition.objects.filter(
                highschool__id__in=school_ids,
                status='active'
            ).select_related('hsadmin__user', 'highschool')

        # Get email template
        subject = fs_config.get('pending_notification_subject', 'Reminder: Section Request Response Needed')
        message_template = fs_config.get('pending_notification_message', '')

        if not message_template:
            summary = "Error: No email message template configured"
            detailed_log['errors'].append(summary)
            return summary, detailed_log

        # Get academic year name
        try:
            academic_year = AcademicYear.objects.get(id=academic_year_id)
            academic_year_name = str(academic_year)
        except AcademicYear.DoesNotExist:
            academic_year_name = ''

        # Build link
        site_url = getattr(django_settings, 'SITE_URL', '')
        link = f"{site_url}/highschool_admin/future_sections/"

        # Send emails
        seen_emails = set()  # Avoid duplicate emails

        for admin_pos in admins:
            user = admin_pos.hsadmin.user
            email = user.email

            if not email or email in seen_emails:
                continue
            seen_emails.add(email)

            highschool = admin_pos.highschool
            pending_count = pending_counts.get(str(highschool.id), 0)

            try:
                template = Template(message_template)
                context = Context({
                    'admin_first_name': user.first_name,
                    'admin_last_name': user.last_name,
                    'highschool': highschool.name,
                    'academic_year': academic_year_name,
                    'pending_count': pending_count,
                    'link': link
                })
                text_body = template.render(context)

                # Render HTML email using standard template
                html_template = get_template('cis/email.html')
                html_body = html_template.render({'message': text_body})

                # DEBUG mode: redirect to test email address
                to = [email]
                if getattr(django_settings, 'DEBUG', True):
                    to = ['kadaji@gmail.com']

                send_html_mail(
                    subject,
                    text_body,
                    html_body,
                    django_settings.DEFAULT_FROM_EMAIL,
                    to
                )

                emails_sent += 1
                detailed_log['emails_sent'].append({
                    'email': email,
                    'highschool': highschool.name,
                    'pending_count': pending_count
                })
            except Exception as e:
                errors += 1
                detailed_log['errors'].append({
                    'email': email,
                    'highschool': highschool.name,
                    'error': str(e)
                })

        summary = f"Sent {emails_sent} email(s), {errors} error(s)"
        return summary, detailed_log


class FutureSection(models.Model):
    """Section info for each instructor"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Local reference to FutureCourse (same app)
    future_course = models.ForeignKey(FutureCourse, on_delete=models.CASCADE)

    section_info = JSONField(blank=True)
    added_on = models.DateField(auto_now_add=True)

    @property
    def teaching_or_not(self):
        return 'Yes' if self.section_info.get('teaching') == 'yes' else 'No'

    @property
    def number_of_sections(self):
        return self.section_info.get('number_of_sections')

    @property
    def estimated_enrollment(self):
        return self.section_info.get('estimated_enrollment', '-')

    @staticmethod
    def export_instructor_survey_export():
        """
        Export instructor survey links
        """
        from cis.models.teacher import TeacherCourseCertificate

        file_name = "instructor_survey_export.csv"

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{file_name}"'
        writer = csv.writer(response)

        fields = [
            'School',
            'Instructor First Name',
            'Instructor Last Name',
            'Email',
            'EMPLID',
            'Link'
        ]
        records = TeacherCourseCertificate.objects.filter(
            course__status='Active'
        ).exclude(
            teacher_highschool__teacher__in=FutureSection.objects.filter(
            ).values('teacher_course__teacher_highschool__teacher')
        ).distinct('teacher_highschool__teacher')

        writer.writerow(fields)

        for record in records:
            row = []
            row.append(record.teacher_highschool.highschool.name)
            row.append(record.teacher_highschool.teacher.user.first_name)
            row.append(record.teacher_highschool.teacher.user.last_name)
            row.append(record.teacher_highschool.teacher.user.email)
            row.append(record.teacher_highschool.teacher.user.psid)
            row.append(
                reverse(
                    'instructor:course_schedule',
                    kwargs={
                        'instructor': record.teacher_highschool.teacher.id}))

            writer.writerow(row)

        return response

    @staticmethod
    def export_to_excel(records):
        """
        Write records to an Excel file
        """
        file_name = "future_sections.csv"
        fields = {
            'future_course.id': 'ID',
            'future_course.academic_year': "Academic Year",
            'teacher_course.teacher_highschool.teacher.user.first_name': 'Instructor Firstname',
            'teacher_course.teacher_highschool.teacher.user.last_name': 'Instructor Lastname',
            'teacher_course.teacher_highschool.teacher.user': 'Instructor Email',
            'teacher_course.teacher_highschool.teacher.user.psid': 'EMPLID',
            'teacher_course.course': 'Course',
            'teacher_course.teacher_highschool.highschool': 'School',
            'added_on': 'Added On',
            "section_info['teaching']": 'Teaching',
            'starting_date': 'Starting Date',
            'ending_date': 'Ending Date',
            'estimated_enrollment': 'Estimated Enrollement',
            'length_change': 'Length Change',
            'access_to_resources': 'Access To Resources',
            'access_needed_date': 'Access Needed By',
            'taught_by_another': 'Taught By Another',
            'another_instructor': 'Another Instructor Name',
        }

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{file_name}"'
        writer = csv.writer(response)

        writer.writerow(fields.values())

        for record in records:
            row = []
            row.append(record.pk)
            row.append(record.future_course.academic_year)
            row.append(record.teacher_course.teacher_highschool.teacher.user.first_name)
            row.append(record.teacher_course.teacher_highschool.teacher.user.last_name)
            row.append(record.teacher_course.teacher_highschool.teacher.user.email)
            row.append(record.teacher_course.teacher_highschool.teacher.user.psid)
            row.append(record.teacher_course.course)
            row.append(record.teacher_course.teacher_highschool.highschool.name)
            row.append(record.added_on)

            row.append(record.section_info.get('teaching'))
            row.append(record.section_info.get('starting_date'))
            row.append(record.section_info.get('ending_date'))
            row.append(record.section_info.get('estimated_enrollment'))
            row.append(record.section_info.get('length_change'))
            row.append(record.section_info.get('access_to_resources'))
            row.append(record.section_info.get('access_date'))

            row.append(record.section_info.get('taught_by_another'))
            row.append(record.section_info.get('other_instructor'))
            writer.writerow(row)

        return response
