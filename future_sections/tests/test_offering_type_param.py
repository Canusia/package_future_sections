"""The add-teacher course list filter travels as `offering_type`.

It used to be posted as `course_type`, which now collides with the
tenant-configured `course_type` field on the Add Teacher form: both would sit
in the same POST body, and the user's answer ("Dual Credit") would be read as
the course-list filter. The filter is therefore taken from the query string
only, with the legacy key still accepted so a browser holding a cached copy of
the older JS keeps working.
"""
from django.test import SimpleTestCase
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from future_sections.future_sections.views.api import resolve_offering_type


class ResolveOfferingTypeTests(SimpleTestCase):

    def _request(self, path='/x/', data=None):
        factory = APIRequestFactory()
        if data is None:
            return Request(factory.get(path))
        return Request(factory.post(path, data),
                       parsers=[MultiPartParser(), FormParser()])

    def test_defaults_to_pathways(self):
        self.assertEqual(resolve_offering_type(self._request()), 'pathways')

    def test_reads_offering_type_from_the_query_string(self):
        self.assertEqual(
            resolve_offering_type(self._request('/x/?offering_type=cccl')),
            'cccl')

    def test_legacy_course_type_query_key_still_works(self):
        self.assertEqual(
            resolve_offering_type(
                self._request('/x/?course_type=facilitator')),
            'facilitator')

    def test_posted_course_type_answer_is_not_mistaken_for_the_filter(self):
        # The form's own course_type field rides in the POST body.
        request = self._request('/x/?offering_type=cccl',
                                data={'course_type': 'dual'})
        self.assertEqual(resolve_offering_type(request), 'cccl')

    def test_posted_course_type_answer_alone_falls_back_to_the_default(self):
        request = self._request('/x/', data={'course_type': 'dual'})
        self.assertEqual(resolve_offering_type(request), 'pathways')
