"""
Pending Section Requests - High School Admin Export Report

Exports HSAdministratorPosition records for schools that have pending section requests.
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
from cis.models.highschool_administrator import HSAdministratorPosition, HSPosition
from ..models import FutureCourse
from ..settings.future_sections import future_sections as fs_settings


class pending_future_classes(forms.Form):
    academic_year = forms.ModelChoiceField(
        queryset=None
    )

    positions = forms.ModelMultipleChoiceField(
        queryset=None,
        label='Position(s)'
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
        self.fields['positions'].queryset = HSPosition.objects.all().order_by('name')

    def run(self, task, data):
        academic_year_id = data['academic_year'][0]
        position_ids = data['positions']

        fs_setting_config = fs_settings.from_db()

        # Get certificate IDs that have already submitted
        received_records = FutureCourse.objects.filter(
            academic_year__id=academic_year_id
        ).values_list('teacher_course__certificate_id', flat=True)

        # Get high schools with pending requests
        pending_highschools = TeacherCourseCertificate.objects.filter(
            course__status__in=fs_setting_config.get('course_status', []),
            status__in=fs_setting_config.get('teacher_course_status', [])
        ).exclude(
            certificate_id__in=received_records
        ).values_list(
            'teacher_highschool__highschool__id', flat=True
        )

        # Get administrator positions for those high schools
        records = HSAdministratorPosition.objects.filter(
            highschool__id__in=pending_highschools,
            position__id__in=position_ids
        )

        file_name = "pending_future_class_sections_hs_admins-" + str(datetime.datetime.now()) + ".csv"

        fields = {
            'highschool.name': 'High School',
            'highschool.status': 'High School Status',
            'highschool.code': 'CEEB Code',
            'highschool.address1': 'Address1',
            'highschool.address2': 'Address2',
            'highschool.city': 'City',
            'highschool.state': 'State',
            'highschool.postal_code': 'Zip',
            'highschool.primary_phone': 'Phone',
            'highschool.sau': 'SAU',

            'hsadmin.user.last_name': 'Last Name',
            'hsadmin.user.first_name': 'First Name',
            'hsadmin.user.email': 'Email',
            'hsadmin.user.primary_phone': 'Phone',

            'position.name': 'Position',
            'status': 'Administrator Status'
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
