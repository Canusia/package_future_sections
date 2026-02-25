"""
Pending Section Requests - Course(s) Export Report

Exports TeacherCourseCertificate records that have NOT yet submitted section requests.
"""
import datetime

from django import forms
from django.urls import reverse_lazy
from django.core.files.base import ContentFile

from cis.backends.storage_backend import PrivateMediaStorage
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

from cis.utils import export_to_excel
from cis.models.term import AcademicYear
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

        file_name = "pending_future_class_courses-" + str(datetime.datetime.now()) + ".csv"

        fields = {
            'pk': 'ID',
            'teacher_highschool.highschool': 'School',
            'teacher_highschool.teacher.user.last_name': 'Teacher Last Name',
            'teacher_highschool.teacher.user.first_name': 'Teacher First Name',
            'course.name': 'Course Name',
            'status': 'Status',
        }

        http_response = export_to_excel(
            file_name,
            records,
            fields
        )

        path = "reports/" + str(task.id) + "/" + file_name
        media_storage = PrivateMediaStorage()

        path = media_storage.save(path, ContentFile(http_response.content))
        path = media_storage.url(path)

        return path
