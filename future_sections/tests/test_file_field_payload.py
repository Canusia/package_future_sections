from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, RequestFactory

from ..utils import build_section_info_from_formset as build_sections_payload


class _FakeForm:
    def __init__(self, cleaned_data):
        self.cleaned_data = cleaned_data


class _FakeCourse:
    id = 'abc-123'

    def __init__(self, section_info=None):
        self.section_info = section_info


class _FakeStorage:
    def save(self, name, content):
        return name

    def url(self, name):
        return f'https://files.test/{name}'


def _post(files=None):
    factory = RequestFactory()
    request = factory.post('/', data=files or {})
    return request


class FilePayloadTests(SimpleTestCase):
    def _run(self, forms, files=None, course=None):
        request = _post(files)
        with mock.patch(
            'cis.backends.storage_backend.PrivateMediaStorage',
            _FakeStorage,
        ):
            return build_sections_payload(
                request, forms, course if course is not None else _FakeCourse())

    def test_uploaded_file_is_stored_under_the_field_name(self):
        upload = SimpleUploadedFile('rubric.pdf', b'data')
        sections = self._run(
            [_FakeForm({'term': 't1', 'assessment_upload': None})],
            files={'form-0-assessment_upload': upload},
        )
        self.assertEqual(
            sections[0]['assessment_upload'],
            'https://files.test/future_section/abc-123/rubric.pdf')

    def test_existing_url_is_carried_forward_when_no_new_upload(self):
        course = _FakeCourse(section_info={'sections': [
            {'assessment_upload': 'https://files.test/old.pdf'},
        ]})
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': None,
            'assessment_upload_existing': 'https://files.test/old.pdf',
        })], course=course)
        self.assertEqual(sections[0]['assessment_upload'],
                         'https://files.test/old.pdf')

    def test_companion_key_is_not_persisted(self):
        course = _FakeCourse(section_info={'sections': [
            {'assessment_upload': 'https://files.test/old.pdf'},
        ]})
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': None,
            'assessment_upload_existing': 'https://files.test/old.pdf',
        })], course=course)
        self.assertNotIn('assessment_upload_existing', sections[0])

    def test_existing_url_not_on_record_is_dropped(self):
        course = _FakeCourse(section_info={'sections': [
            {'assessment_upload': 'https://files.test/old.pdf'},
        ]})
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': None,
            'assessment_upload_existing': 'https://evil.test/spoofed.pdf',
        })], course=course)
        self.assertEqual(sections[0]['assessment_upload'], '')

    def test_existing_url_on_a_different_section_index_is_accepted(self):
        course = _FakeCourse(section_info={'sections': [
            {'assessment_upload': 'https://files.test/section-a.pdf'},
            {'assessment_upload': 'https://files.test/section-b.pdf'},
        ]})
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': None,
            'assessment_upload_existing': 'https://files.test/section-b.pdf',
        })], course=course)
        self.assertEqual(sections[0]['assessment_upload'],
                         'https://files.test/section-b.pdf')

    def test_empty_section_info_drops_posted_existing_without_raising(self):
        course = _FakeCourse(section_info=None)
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': None,
            'assessment_upload_existing': 'https://files.test/old.pdf',
        })], course=course)
        self.assertEqual(sections[0]['assessment_upload'], '')

        course = _FakeCourse(section_info={})
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': None,
            'assessment_upload_existing': 'https://files.test/old.pdf',
        })], course=course)
        self.assertEqual(sections[0]['assessment_upload'], '')

    def test_new_upload_replaces_the_existing_url(self):
        upload = SimpleUploadedFile('new.pdf', b'data')
        sections = self._run(
            [_FakeForm({
                'term': 't1',
                'assessment_upload': None,
                'assessment_upload_existing': 'https://files.test/old.pdf',
            })],
            files={'form-0-assessment_upload': upload},
        )
        self.assertEqual(
            sections[0]['assessment_upload'],
            'https://files.test/future_section/abc-123/new.pdf')

    def test_hidden_file_field_value_is_preserved(self):
        # When the field is not visible it arrives as a plain URL string.
        course = _FakeCourse(section_info={'sections': [
            {'assessment_upload': 'https://files.test/kept.pdf'},
        ]})
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': 'https://files.test/kept.pdf',
        })], course=course)
        self.assertEqual(sections[0]['assessment_upload'],
                         'https://files.test/kept.pdf')

    def test_hidden_file_field_value_not_on_record_is_dropped(self):
        course = _FakeCourse(section_info={'sections': [
            {'assessment_upload': 'https://files.test/kept.pdf'},
        ]})
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': 'https://evil.test/spoofed.pdf',
        })], course=course)
        self.assertEqual(sections[0]['assessment_upload'], '')

    def test_hidden_file_field_value_on_a_different_section_index_is_accepted(self):
        course = _FakeCourse(section_info={'sections': [
            {'assessment_upload': 'https://files.test/section-a.pdf'},
            {'assessment_upload': 'https://files.test/section-b.pdf'},
        ]})
        sections = self._run([_FakeForm({
            'term': 't1',
            'assessment_upload': 'https://files.test/section-b.pdf',
        })], course=course)
        self.assertEqual(sections[0]['assessment_upload'],
                         'https://files.test/section-b.pdf')

    def test_missing_file_yields_empty_string(self):
        sections = self._run([_FakeForm({'term': 't1'})])
        self.assertEqual(sections[0]['assessment_upload'], '')

    def test_rows_without_a_term_are_still_skipped(self):
        sections = self._run([_FakeForm({'term': ''})])
        self.assertEqual(sections, [])

    def test_syllabus_still_lands_in_the_file_key(self):
        upload = SimpleUploadedFile('syllabus.pdf', b'data')
        sections = self._run(
            [_FakeForm({'term': 't1', 'syllabus': None})],
            files={'form-0-syllabus': upload},
        )
        self.assertEqual(
            sections[0]['file'],
            'https://files.test/future_section/abc-123/syllabus.pdf')
        self.assertNotIn('syllabus', sections[0])
