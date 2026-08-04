"""
Coverage for C1: the teaching formset must be bound with request.FILES, or a
required FileField (e.g. assessment_upload) becomes permanently unsubmittable
— even when the user did attach a file, and even when a URL is already
stored on the section.

These tests exercise the real TeacherCourseSectionForm / formset validation
path (not the `_FakeForm` shortcuts used in test_file_field_payload.py),
mirroring exactly how views/ce.py and views/api.py construct and bind the
formset on POST.
"""
import json
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import formset_factory
from django.test import TestCase, RequestFactory

from cis.models.settings import Setting
from cis.models.term import AcademicYear, Term
from future_sections.future_sections.forms import (
    TeacherCourseSectionForm, TeacherCourseBaseLinkFormSet,
)
from future_sections.future_sections.utils import (
    build_section_info_from_formset,
)


class _FakeStorage:
    def save(self, name, content):
        return name

    def url(self, name):
        return f'https://files.test/{name}'


class _FakeCourse:
    id = 'course-1'

    def __init__(self, section_info=None):
        self.section_info = section_info


class _FormsetBindingMixin:
    def _make_setting(self, required=('term', 'assessment_upload')):
        self.academic_year = AcademicYear.objects.create(name='2026-2027')
        self.term = Term.objects.create(
            code='FA26', label='Fall 2026', academic_year=self.academic_year)
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'academic_year': str(self.academic_year.id),
                'teaching_form_config': json.dumps({
                    'fields': ['term', 'assessment_upload'],
                    'required': list(required),
                }),
            },
        )

    def _management_data(self, total=1, initial=0):
        return {
            'form-TOTAL_FORMS': str(total),
            'form-INITIAL_FORMS': str(initial),
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
        }

    def _formset(self, data, files=None):
        TeachingFormSet = formset_factory(
            TeacherCourseSectionForm,
            formset=TeacherCourseBaseLinkFormSet,
            extra=0,
        )
        return TeachingFormSet(data, files or {})


class RequiredFileFieldValidationTests(_FormsetBindingMixin, TestCase):
    def test_required_assessment_upload_validates_when_file_posted(self):
        self._make_setting()
        upload = SimpleUploadedFile(
            'assessment.pdf', b'bytes', content_type='application/pdf')
        data = self._management_data()
        data['form-0-term'] = str(self.term.id)
        formset = self._formset(
            data, files={'form-0-assessment_upload': upload})
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_required_assessment_upload_errors_when_nothing_posted_or_stored(self):
        self._make_setting()
        data = self._management_data()
        data['form-0-term'] = str(self.term.id)
        formset = self._formset(data)
        self.assertFalse(formset.is_valid())
        self.assertIn('assessment_upload', formset.errors[0])

    def test_stored_assessment_url_saves_without_reupload_when_required(self):
        self._make_setting()
        stored_url = 'https://files.test/old.pdf'
        data = self._management_data()
        data['form-0-term'] = str(self.term.id)
        data['form-0-assessment_upload_existing'] = stored_url
        formset = self._formset(data)
        self.assertTrue(formset.is_valid(), formset.errors)

        course = _FakeCourse(section_info={
            'sections': [{'assessment_upload': stored_url}],
        })
        factory = RequestFactory()
        request = factory.post('/', data={})
        with mock.patch(
            'cis.backends.storage_backend.PrivateMediaStorage',
            _FakeStorage,
        ):
            sections = build_section_info_from_formset(
                request, formset, course)

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]['assessment_upload'], stored_url)

    def test_no_uploadedfile_reaches_the_payload(self):
        self._make_setting()
        upload = SimpleUploadedFile(
            'assessment.pdf', b'bytes', content_type='application/pdf')
        data = self._management_data()
        data['form-0-term'] = str(self.term.id)
        request_files = {'form-0-assessment_upload': upload}
        formset = self._formset(data, files=request_files)
        self.assertTrue(formset.is_valid(), formset.errors)

        factory = RequestFactory()
        request = factory.post('/', data={})
        request.FILES.update(request_files)
        with mock.patch(
            'cis.backends.storage_backend.PrivateMediaStorage',
            _FakeStorage,
        ):
            sections = build_section_info_from_formset(
                request, formset, _FakeCourse())

        self.assertEqual(len(sections), 1)
        for value in sections[0].values():
            self.assertNotIsInstance(value, SimpleUploadedFile)
        self.assertEqual(
            sections[0]['assessment_upload'],
            'https://files.test/future_section/course-1/assessment.pdf')

    def test_syllabus_path_is_unaffected(self):
        # syllabus is hardcoded required=False (forms.py), so it must
        # validate cleanly with no file and no formset FILES binding for it.
        self.academic_year = AcademicYear.objects.create(name='2027-2028')
        self.term = Term.objects.create(
            code='FA27', label='Fall 2027', academic_year=self.academic_year)
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'academic_year': str(self.academic_year.id),
                'teaching_form_config': json.dumps({
                    'fields': ['term'],
                    'required': ['term'],
                    'show_syllabus': True,
                }),
            },
        )
        data = self._management_data()
        data['form-0-term'] = str(self.term.id)
        formset = self._formset(data)
        self.assertTrue(formset.is_valid(), formset.errors)
