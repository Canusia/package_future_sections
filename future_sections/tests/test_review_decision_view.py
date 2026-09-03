from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.test import TestCase
from django.urls import reverse

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.teacher import Teacher, TeacherCourseCertificate, TeacherHighSchool
from cis.models.highschool import HighSchool
from cis.models.term import AcademicYear

from ..models import FutureCourse
from ..review.helpers import open_review_round, record_decision


def _user(email):
    return CustomUser.objects.create(username=email, email=email)


class SectionRequestDecisionViewTests(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django_login_history.models import post_login
        user_logged_in.disconnect(post_login)
        cls._post_login = post_login

    @classmethod
    def tearDownClass(cls):
        user_logged_in.connect(cls._post_login)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Main', code='M')
        cls.course = Course.objects.create(
            name='A1', title='Alpha', cohort=cls.cohort, catalog_number='101',
            credit_hours=3, campus=cls.campus, status='Active')
        Group.objects.get_or_create(name='faculty')
        Group.objects.get_or_create(name='instructor')
        hs = HighSchool.objects.create(name='Test HS')
        teacher = Teacher.objects.create(user=_user('t@x.com'))
        ths = TeacherHighSchool.objects.create(teacher=teacher, highschool=hs)
        cls.tc = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=cls.course, status='Applicant')

    def setUp(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={'require_review': '1', 'reviewer_roles': ['Faculty'],
                   'assign_mentor': 'No'})
        self.fc = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=self.tc, status='submitted')

    def _reviewer(self, email, role='Faculty', status='Active'):
        u = _user(email)
        u.groups.add(Group.objects.get(name='faculty'))
        CourseAdministrator.objects.create(
            course=self.course, user=u, role=role, status=status)
        return u

    def test_posting_a_decision_records_the_row(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        self.client.force_login(a)
        resp = self.client.post(
            reverse('future_sections_faculty:section_request_detail', args=[str(self.fc.id)]),
            {'decision': 'approved', 'comment': 'looks fine'})
        self.assertEqual(resp.status_code, 302)
        row = self.fc.reviews.get(reviewer=a)
        self.assertEqual(row.decision, 'approved')
        self.assertEqual(row.comment, 'looks fine')

    def test_the_last_decision_advances_the_request(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        self.client.force_login(a)
        self.client.post(
            reverse('future_sections_faculty:section_request_detail', args=[str(self.fc.id)]),
            {'decision': 'approved', 'comment': ''})
        self.fc.refresh_from_db()
        self.assertEqual(self.fc.status, 'reviewed')

    def test_a_second_reviewer_sees_the_first_decision(self):
        a = self._reviewer('a@x.com')
        d = self._reviewer('d@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved', comment='mine')
        self.client.force_login(d)
        resp = self.client.get(reverse('future_sections_faculty:section_request_detail', args=[str(self.fc.id)]))
        self.assertContains(resp, 'mine')

    def test_a_non_reviewer_gets_404(self):
        self._reviewer('a@x.com')
        open_review_round(self.fc)
        outsider = self._reviewer('out@x.com')
        self.client.force_login(outsider)
        resp = self.client.get(reverse('future_sections_faculty:section_request_detail', args=[str(self.fc.id)]))
        self.assertEqual(resp.status_code, 404)
