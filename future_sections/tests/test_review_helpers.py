from django.test import TestCase
from django.contrib.auth.models import Group

from cis.models.customuser import CustomUser
from cis.models.course import Course, CourseAdministrator, Cohort
from cis.models.term import AcademicYear
from cis.models.highschool import HighSchool
from cis.models.district import District
from cis.models.teacher import Teacher, TeacherHighSchool, TeacherCourseCertificate
from cis.models.settings import Setting

from ..models import FutureCourse
from ..review.helpers import (
    visible_future_courses_for,
    create_or_attach_mentor,
    get_reviewer_roles,
    get_mentor_role,
)


def _world():
    Group.objects.get_or_create(name='faculty')
    Group.objects.get_or_create(name='instructor')
    reviewer = CustomUser.objects.create(
        username='rev@example.com', email='rev@example.com',
        first_name='Rev', last_name='Iewer',
    )
    cohort = Cohort.objects.create(designator='ENG', name='English')
    course = Course.objects.create(
        cohort=cohort, catalog_number='101', title='Comp I',
        name='ENG 101', credit_hours=3, status='Active',
    )
    ay = AcademicYear.objects.create(name='2025-2026')
    district = District.objects.create(name='D')
    hs = HighSchool.objects.create(name='HS', district=district)
    teacher_user = CustomUser.objects.create(
        username='t@example.com', email='t@example.com',
        first_name='T', last_name='Eacher')
    teacher = Teacher.objects.create(user=teacher_user)
    ths = TeacherHighSchool.objects.create(teacher=teacher, highschool=hs)
    tcc = TeacherCourseCertificate.objects.create(
        teacher_highschool=ths, course=course, status='Teaching')
    fc = FutureCourse.objects.create(teacher_course=tcc, academic_year=ay)
    return {'reviewer': reviewer, 'course': course, 'fc': fc}


class VisibleCoursesHonorsSettingsTests(TestCase):
    def test_dean_visible_when_dean_is_in_reviewer_roles(self):
        w = _world()
        Setting.objects.create(
            key='cis_future_sections',
            value={'reviewer_roles': ['Dean']},
        )
        CourseAdministrator.objects.create(
            course=w['course'], user=w['reviewer'], role='Dean', status='Active')
        qs = visible_future_courses_for(w['reviewer'])
        self.assertIn(w['fc'], list(qs))

    def test_dean_hidden_when_only_faculty_is_in_reviewer_roles(self):
        w = _world()
        Setting.objects.create(
            key='cis_future_sections',
            value={'reviewer_roles': ['Faculty']},
        )
        CourseAdministrator.objects.create(
            course=w['course'], user=w['reviewer'], role='Dean', status='Active')
        qs = visible_future_courses_for(w['reviewer'])
        self.assertNotIn(w['fc'], list(qs))

    def test_default_roles_when_no_setting(self):
        # Backward-compat: if the setting row doesn't exist, fall back to
        # ('Faculty', 'Dept. Chair', 'Dean').
        self.assertEqual(
            get_reviewer_roles(),
            ['Faculty', 'Dept. Chair', 'Dean'],
        )

    def test_mentor_default_role_default(self):
        self.assertEqual(get_mentor_role(), 'Faculty')


class CreateMentorUsesConfiguredRoleTests(TestCase):
    def test_course_administrator_role_matches_setting(self):
        w = _world()
        Setting.objects.create(
            key='cis_future_sections',
            value={'mentor_default_role': 'Dept. Chair'},
        )
        user = create_or_attach_mentor(
            w['course'], name='New Mentor', email='nm@example.com',
            role='Dept. Chair',
        )
        ca = CourseAdministrator.objects.get(course=w['course'], user=user)
        self.assertEqual(ca.role, 'Dept. Chair')
        self.assertEqual(ca.status, 'Active')
        # User still goes through FacultyCoordinator + faculty group:
        self.assertTrue(user.groups.filter(name='faculty').exists())
