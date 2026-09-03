"""The live HS-admin course-requests payload must surface the review lock.

This is the *live* endpoint -- `CourseRequestViewSet.list()` in
`future_sections/views/api.py`, routed at
`future_sections_highschool_admin:course-requests-list` -- unlike the
`highschool_admin` submodule's own same-named duplicate, which is dead code
(no URL routes to its page/template, though its API viewset is still
reachable as a legacy `course-actions` endpoint and separately guarded).

Once CE marks a request `pending_review` (or `reviewed`), the school-facing
table must stop offering Edit/Delete on that row -- the server already
refuses the write (`assert_editable`), this makes the UI agree.
"""
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.test import TestCase
from django.urls import reverse

try:
    from django_login_history.models import post_login as _login_history_post_login
except Exception:  # pragma: no cover
    _login_history_post_login = None

from cis.models.customuser import CustomUser
from cis.models.course import Cohort, Course
from cis.models.highschool import HighSchool
from cis.models.term import AcademicYear
from cis.models.teacher import Teacher, TeacherHighSchool, TeacherCourseCertificate
from cis.models.highschool_administrator import (
    HSAdministrator, HSAdministratorPosition, HSPosition,
)

from ..models import FutureCourse
from . import PKG


class CourseRequestLockPayloadTests(TestCase):
    @classmethod
    def setUpClass(cls):
        if _login_history_post_login is not None:
            user_logged_in.disconnect(_login_history_post_login)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if _login_history_post_login is not None:
            user_logged_in.connect(_login_history_post_login)

    @classmethod
    def setUpTestData(cls):
        Group.objects.get_or_create(name='highschool_admin')
        Group.objects.get_or_create(name='instructor')

        cls.hs = HighSchool.objects.create(name='HS Alpha')

        cls.user = CustomUser.objects.create(
            username='counselor@example.com', email='counselor@example.com',
            first_name='Coun', last_name='Selor', is_active=True)
        cls.user.groups.add(Group.objects.get(name='highschool_admin'))
        hsadmin = HSAdministrator.objects.create(user=cls.user)
        HSAdministratorPosition.objects.create(
            hsadmin=hsadmin, highschool=cls.hs,
            position=HSPosition.objects.create(name='Counselor'),
            status='Active')

        cls.ay = AcademicYear.objects.create(name='2025-2026')

        cohort = Cohort.objects.create(name='Default Cohort', designator='DC')

        teacher_user = CustomUser.objects.create(
            username='teach@example.com', email='teach@example.com',
            first_name='Tea', last_name='Cher', is_active=True)
        teacher = Teacher.objects.create(user=teacher_user)
        teacher_hs = TeacherHighSchool.objects.create(
            teacher=teacher, highschool=cls.hs)

        locked_course = Course.objects.create(
            name='ENG101', title='English 101', catalog_number='101',
            cohort=cohort, credit_hours=3, status='Active')
        cls.certificate = TeacherCourseCertificate.objects.create(
            teacher_highschool=teacher_hs, course=locked_course,
            status='Teaching')
        FutureCourse.objects.create(
            teacher_course=cls.certificate, academic_year=cls.ay,
            status='pending_review')

        submitted_course = Course.objects.create(
            name='MTH101', title='Math 101', catalog_number='102',
            cohort=cohort, credit_hours=3, status='Active')
        cls.submitted_certificate = TeacherCourseCertificate.objects.create(
            teacher_highschool=teacher_hs, course=submitted_course,
            status='Teaching')
        FutureCourse.objects.create(
            teacher_course=cls.submitted_certificate, academic_year=cls.ay,
            status='submitted')

        bare_course = Course.objects.create(
            name='HIS101', title='History 101', catalog_number='103',
            cohort=cohort, credit_hours=3, status='Active')
        cls.bare_certificate = TeacherCourseCertificate.objects.create(
            teacher_highschool=teacher_hs, course=bare_course,
            status='Teaching')

    def _payload_row_for(self, certificate):
        self.client.force_login(self.user)
        queryset = TeacherCourseCertificate.objects.filter(
            pk__in=[
                self.certificate.pk,
                self.submitted_certificate.pk,
                self.bare_certificate.pk,
            ])
        fs_config = {
            'academic_year': str(self.ay.id),
            'previous_academic_year': None,
            'prev_year_class_status': [],
            'course_display_template': '{course_title}',
        }
        with patch(f'{PKG}.views.api.get_course_certificates_for_user',
                   return_value=queryset), \
             patch(f'{PKG}.views.api.get_fs_config', return_value=fs_config):
            resp = self.client.get(
                reverse('future_sections_highschool_admin:course-requests-list'))
        self.assertEqual(resp.status_code, 200)
        rows = {r['certificate_id']: r for r in resp.json()}
        return rows[str(certificate.certificate_id)]

    def test_payload_reports_the_review_status(self):
        row = self._payload_row_for(self.certificate)
        self.assertEqual(row['review_status'], 'pending_review')
        self.assertTrue(row['is_locked'])

    def test_a_submitted_request_is_not_locked(self):
        row = self._payload_row_for(self.submitted_certificate)
        self.assertEqual(row['review_status'], 'submitted')
        self.assertFalse(row['is_locked'])

    def test_a_certificate_with_no_request_is_not_locked(self):
        row = self._payload_row_for(self.bare_certificate)
        self.assertIsNone(row['review_status'])
        self.assertFalse(row['is_locked'])
