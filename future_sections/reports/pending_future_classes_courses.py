"""
Pending Section Requests - Course(s) Export Report

Exports TeacherCourseCertificate records that have NOT yet submitted section requests.
"""
import io
import csv
import datetime

from django import forms
from django.db.models import Count
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.core.files.base import ContentFile

from cis.backends.storage_backend import PrivateMediaStorage
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

from cis.utils import get_field
from cis.models.term import AcademicYear
from cis.models.section import ClassSection
from cis.models.teacher import TeacherCourseCertificate
from ..models import FutureCourse
from ..settings.future_sections import future_sections as fs_settings


class pending_future_classes_courses(forms.Form):
    academic_year = forms.ModelChoiceField(
        queryset=None
    )

    roles = []
    request = None

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.request = request

        self.helper = FormHelper()
        self.helper.attrs = {'target': '_blank'}
        self.helper.form_method = 'POST'
        self.helper.add_input(Submit('submit', 'Generate Export'))

        if self.request:
            self.helper.form_action = reverse_lazy(
                'report:run_report', args=[request.GET.get('report_id')]
            )

        self.fields['academic_year'].queryset = AcademicYear.objects.all().order_by('-name')

    def run(self, task, data):
        academic_year_id = data['academic_year'][0]

        fs_setting_config = fs_settings.from_db()

        # Get certificate IDs that have already submitted
        received_records = FutureCourse.objects.filter(
            academic_year__id=academic_year_id
        ).values_list('teacher_course__certificate_id', flat=True)

        # Get certificates that haven't submitted yet
        records = TeacherCourseCertificate.objects.filter(
            course__status__in=fs_setting_config.get('course_status', []),
            status__in=fs_setting_config.get('teacher_course_status', [])
        ).exclude(
            certificate_id__in=received_records
        )

        # Build previous year section counts per (course, highschool)
        previous_academic_year_id = fs_setting_config.get('previous_academic_year')
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

        file_name = "pending_future_class_courses-" + str(datetime.datetime.now()) + ".csv"

        fields = {
            'pk': 'ID',
            'teacher_highschool.highschool': 'School',
            'teacher_highschool.teacher.user.last_name': 'Teacher Last Name',
            'teacher_highschool.teacher.user.first_name': 'Teacher First Name',
            'course.name': 'Course Name',
            'status': 'Status',
        }

        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=',')

        # Header
        writer.writerow(list(fields.values()) + ['Previous Year Sections'])

        for record in records:
            row = []
            for key in fields.keys():
                row.append(force_str(get_field(record, key)))

            # Previous year sections
            prev_key = f"{record.course_id}_{record.teacher_highschool.highschool_id}"
            prev_sections = prev_year_lookup.get(prev_key, [])
            if prev_sections:
                prev_display = '; '.join(
                    f"{s['term_name']}: {s['count']}" for s in prev_sections
                )
            else:
                prev_display = ''
            row.append(prev_display)

            writer.writerow(row)

        path = "reports/" + str(task.id) + "/" + file_name
        media_storage = PrivateMediaStorage()

        path = media_storage.save(path, ContentFile(stream.getvalue().encode('utf-8')))
        path = media_storage.url(path)

        return path
