from django.contrib.auth.models import Group
from django.test import TestCase

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.teacher import Teacher, TeacherCourseCertificate, TeacherHighSchool
from cis.models.highschool import HighSchool
from cis.models.term import AcademicYear

from ..models import FutureCourse, SectionRequestReview
from ..review.helpers import (
    open_review_round, pending_for, record_decision, reset_review,
    reviewed_for, visible_future_courses_for,
)


def _user(email):
    return CustomUser.objects.create(username=email, email=email)


class ReviewScopingTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Main', code='M')
        cls.course = Course.objects.create(
            name='A1', title='Alpha', cohort=cls.cohort, catalog_number='101',
            credit_hours=3, campus=cls.campus, status='Active')
        Group.objects.get_or_create(name='instructor')
        hs = HighSchool.objects.create(name='Test HS')
        teacher = Teacher.objects.create(user=_user('t@x.com'))
        ths = TeacherHighSchool.objects.create(teacher=teacher, highschool=hs)
        cls.tc = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=cls.course, status='Applicant')

    def setUp(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={'require_review': '1', 'reviewer_roles': ['Faculty']})
        self.fc = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=self.tc, status='submitted')

    def _reviewer(self, email, role='Faculty', status='Active'):
        u = _user(email)
        CourseAdministrator.objects.create(
            course=self.course, user=u, role=role, status=status)
        return u

    def test_pending_holds_live_round_undecided_rows(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        self.assertIn(self.fc, pending_for(a))
        self.assertNotIn(self.fc, reviewed_for(a))

    def test_deciding_moves_it_from_pending_to_reviewed(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        self.assertNotIn(self.fc, pending_for(a))
        self.assertIn(self.fc, reviewed_for(a))

    def test_reviewed_survives_a_ce_reset(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        reset_review(self.fc)
        self.assertIn(self.fc, reviewed_for(a))

    def test_a_course_administrator_with_no_row_sees_nothing(self):
        self._reviewer('a@x.com')
        open_review_round(self.fc)
        latecomer = self._reviewer('late@x.com')
        self.assertNotIn(self.fc, visible_future_courses_for(latecomer))

    def test_a_submitted_request_is_in_nobody_s_pending(self):
        a = self._reviewer('a@x.com')
        self.assertNotIn(self.fc, pending_for(a))

    def test_an_anonymous_user_sees_nothing(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(list(visible_future_courses_for(AnonymousUser())), [])
