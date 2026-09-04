from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in


def _safe_force_login(client, user):
    from django_login_history.models import post_login
    user_logged_in.disconnect(post_login)
    try:
        client.force_login(user)
    finally:
        user_logged_in.connect(post_login)

from cis.models.customuser import CustomUser
from cis.models.course import Course, CourseAdministrator, Cohort
from cis.models.term import AcademicYear
from cis.models.highschool import HighSchool
from cis.models.district import District
from cis.models.teacher import Teacher, TeacherHighSchool, TeacherCourseCertificate
from cis.models.settings import Setting

from ..models import FutureCourse
from ..review.helpers import open_review_round


def _world(reviewer_role='Faculty'):
    Group.objects.get_or_create(name='faculty')
    Group.objects.get_or_create(name='instructor')
    user = CustomUser.objects.create(
        username='u@x.com', email='u@x.com', first_name='U', last_name='X')
    user.set_password('p')
    user.save()
    user.groups.add(Group.objects.get(name='faculty'))
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
        course=course, user=user, role=reviewer_role, status='Active')
    # Visibility is now gated by holding a review row, not just an Active
    # CourseAdministrator row — open the round so the reviewer has one.
    open_review_round(fc)
    return user, fc


class FacultyPortalReviewViewsTests(TestCase):
    def setUp(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={'require_review': 'Yes', 'reviewer_roles': ['Faculty'],
                   'assign_mentor': 'Yes', 'mentor_default_role': 'Faculty'},
        )
        self.user, self.fc = _world()
        self.client = Client()
        _safe_force_login(self.client, self.user)

    def test_list_loads_under_faculty_namespace(self):
        resp = self.client.get(reverse('future_sections_faculty:section_request_list'))
        self.assertEqual(resp.status_code, 200)

    def test_detail_loads_under_faculty_namespace(self):
        resp = self.client.get(reverse(
            'future_sections_faculty:section_request_detail',
            args=[str(self.fc.id)]))
        self.assertEqual(resp.status_code, 200)

    def test_list_404_when_review_disabled(self):
        Setting.objects.filter(key='cis_future_sections').update(
            value={'require_review': 'No', 'reviewer_roles': ['Faculty']})
        resp = self.client.get(reverse('future_sections_faculty:section_request_list'))
        self.assertEqual(resp.status_code, 404)


class CEPortalReviewViewsTests(TestCase):
    def setUp(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={'require_review': 'Yes', 'reviewer_roles': ['Administrator'],
                   'assign_mentor': 'No'},
        )
        self.user, self.fc = _world(reviewer_role='Administrator')
        # CE namespace gates on the 'ce' group via user_has_cis_role.
        Group.objects.get_or_create(name='ce')
        self.user.groups.add(Group.objects.get(name='ce'))
        self.client = Client()
        _safe_force_login(self.client, self.user)

    def test_list_loads_under_ce_namespace(self):
        resp = self.client.get(reverse('future_sections_ce:section_request_list'))
        self.assertEqual(resp.status_code, 200)
