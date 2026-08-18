from django.test import TestCase
from django.contrib.auth.models import Group

from rest_framework.test import APIRequestFactory, force_authenticate

from cis.models.customuser import CustomUser
from cis.models.course import Course, CourseAdministrator, Cohort
from cis.models.term import AcademicYear
from cis.models.highschool import HighSchool
from cis.models.district import District
from cis.models.teacher import Teacher, TeacherHighSchool, TeacherCourseCertificate
from cis.models.settings import Setting

from ..models import FutureCourse
from ..review.api import SectionRequestViewSet


def _world(reviewer_role='Faculty'):
    Group.objects.get_or_create(name='faculty')
    Group.objects.get_or_create(name='instructor')
    reviewer = CustomUser.objects.create(
        username='r@x.com', email='r@x.com', first_name='R', last_name='X')
    cohort = Cohort.objects.create(designator='ENG', name='English')
    course = Course.objects.create(
        cohort=cohort, catalog_number='101', title='Comp I',
        name='ENG 101', credit_hours=3, status='Active')
    ay = AcademicYear.objects.create(name='2025-2026')
    district = District.objects.create(name='D')
    hs = HighSchool.objects.create(name='HS', district=district)
    t_user = CustomUser.objects.create(
        username='t@x.com', email='t@x.com', first_name='T', last_name='X')
    teacher = Teacher.objects.create(user=t_user)
    ths = TeacherHighSchool.objects.create(teacher=teacher, highschool=hs)
    tcc = TeacherCourseCertificate.objects.create(
        teacher_highschool=ths, course=course, status='Teaching')
    fc = FutureCourse.objects.create(teacher_course=tcc, academic_year=ay)
    CourseAdministrator.objects.create(
        course=course, user=reviewer, role=reviewer_role, status='Active')
    Setting.objects.create(
        key='cis_future_sections',
        value={'reviewer_roles': [reviewer_role], 'require_review': 'Yes'},
    )
    return reviewer, fc


class SectionRequestViewSetTests(TestCase):
    def test_list_returns_visible_future_courses(self):
        reviewer, fc = _world()
        factory = APIRequestFactory()
        req = factory.get('/api/section_request/', {'tab': 'pending'})
        force_authenticate(req, user=reviewer)
        view = SectionRequestViewSet.as_view({'get': 'list'})
        resp = view(req)
        self.assertEqual(resp.status_code, 200)
        rows = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        ids = [r['id'] for r in rows]
        self.assertIn(str(fc.id), ids)

    def test_list_dean_reviewer_when_setting_includes_dean(self):
        reviewer, fc = _world(reviewer_role='Dean')
        factory = APIRequestFactory()
        req = factory.get('/api/section_request/', {'tab': 'pending'})
        force_authenticate(req, user=reviewer)
        view = SectionRequestViewSet.as_view({'get': 'list'})
        resp = view(req)
        self.assertEqual(resp.status_code, 200)
        rows = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        self.assertIn(str(fc.id), [r['id'] for r in rows])
