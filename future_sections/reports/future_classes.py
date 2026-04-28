"""
Section Requests Export Report

Exports FutureCourse records with dynamic fields based on teaching_form_config settings.
"""
import io
import csv
import datetime

from django import forms
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.core.files.base import ContentFile

from cis.backends.storage_backend import PrivateMediaStorage
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

from cis.utils import get_field
from cis.models.term import AcademicYear
from ..models import FutureCourse


_DECISION_LABELS = {
    'approved': 'Approved',
    'not_approved': 'Not approved',
}


def _show_syllabus_enabled():
    """Whether teaching_form_config in settings has show_syllabus=True."""
    import json
    from ..settings.future_sections import future_sections as fs_settings
    try:
        cfg = json.loads(fs_settings.from_db().get('teaching_form_config', '{}'))
    except (TypeError, ValueError):
        cfg = {}
    return bool(cfg.get('show_syllabus'))


def _faculty_review_cells(record):
    """Return ordered list matching the faculty_review_labels header.

    Empty strings when no review has been recorded.
    """
    review = ((record.section_info or {}).get('faculty_review')) or {}
    if not review.get('decision'):
        return [''] * 6
    mentor = review.get('mentor') or {}
    return [
        _DECISION_LABELS.get(review.get('decision'), review.get('decision', '')),
        mentor.get('name', '') or '',
        mentor.get('email', '') or '',
        review.get('reviewer_name', '') or '',
        review.get('reviewed_on', '') or '',
        review.get('comment', '') or '',
    ]


class future_classes(forms.Form):
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

        records = FutureCourse.objects.filter(
            academic_year__id=academic_year_id
        )

        # Get export configuration from settings
        export_labels = FutureCourse.get_export_labels()
        if records:
            additional_data = records[0].additional_fields()
        else:
            additional_data = []

        # Whether the syllabus column should be included is driven by the
        # show_syllabus toggle in teaching_form_config (same setting that
        # makes the upload field visible on the form).
        show_syllabus = _show_syllabus_enabled()

        file_name = "future_class_sections-" + str(datetime.datetime.now()) + ".csv"

        # Base fields for export
        fields = {
            'pk': 'ID',
            'started_on': 'Added On',
            'academic_year': 'Academic Year',
            'teacher_course.teacher_highschool.highschool': 'High School',
            'teacher_course.teacher_highschool.highschool.code': 'High School CEEB',
            'teacher_course.teacher_highschool.teacher.user.last_name': 'Teacher Last Name',
            'teacher_course.teacher_highschool.teacher.user.first_name': 'Teacher First Name',
            'teacher_course.course.name': 'Course Name',
            'teaching_or_not': 'Offering Course',
        }

        # Faculty review fields appended after the per-section dynamic fields.
        faculty_review_labels = [
            'Faculty Review Decision',
            'Faculty Review Mentor',
            'Faculty Review Mentor Email',
            'Faculty Review Reviewer',
            'Faculty Review Reviewed On',
            'Faculty Review Comment',
        ]

        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=',')

        # Build header labels from settings
        additional_data_labels = [
            export_labels.get(field, field) for field in additional_data
        ]

        syllabus_labels = ['Syllabus'] if show_syllabus else []

        writer.writerow(
            list(fields.values())
            + additional_data_labels
            + syllabus_labels
            + faculty_review_labels
        )

        for record in records:
            row = []

            for key in fields.keys():
                row.append(
                    force_str(get_field(record, key))
                )

            faculty_review_cells = _faculty_review_cells(record)

            if record.teaching_or_not.lower() == 'yes':
                for index, section_info in enumerate(record.section_info.get('sections', [])):
                    crs_row = list(row)

                    for k in additional_data:
                        crs_row.append(record.get_by_property(index, k))

                    if show_syllabus:
                        # Syllabus URL is stored at sections[i]['file'] after upload.
                        crs_row.append(force_str(section_info.get('file', '') or ''))

                    writer.writerow(crs_row + faculty_review_cells)
            else:
                # Pad to align faculty-review cells under the same columns
                # the teaching=yes branch produces.
                pad_count = len(additional_data) + (1 if show_syllabus else 0)
                writer.writerow(
                    row + [''] * pad_count + faculty_review_cells
                )

        path = "reports/" + str(task.id) + "/" + file_name
        media_storage = PrivateMediaStorage()

        path = media_storage.save(path, ContentFile(stream.getvalue().encode('utf-8')))
        path = media_storage.url(path)

        return path
