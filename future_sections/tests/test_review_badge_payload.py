from django.contrib.auth.models import Group
from django.test import TestCase

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.teacher import Teacher, TeacherCourseCertificate, TeacherHighSchool
from cis.models.highschool import HighSchool
from cis.models.term import AcademicYear

from ..models import FutureCourse
from ..review.helpers import open_review_round, record_decision, reset_review
from ..serializers import FutureCourseSerializer


def _user(email):
    return CustomUser.objects.create(username=email, email=email)


class ReviewBadgePayloadTests(TestCase):

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

    def test_no_review_round_yields_none(self):
        payload = FutureCourseSerializer(self.fc).data
        self.assertIsNone(payload['section_display']['review'])

    def test_counts_reflect_the_live_round(self):
        a = self._reviewer('a@x.com')
        self._reviewer('d@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        review = FutureCourseSerializer(self.fc).data['section_display']['review']
        reviewers = review.pop('reviewers')
        self.assertEqual(review, {'round': 1, 'total': 2, 'decided': 1,
                                  'approved': 1, 'not_approved': 0})
        self.assertEqual(len(reviewers), 2)

    def test_an_earlier_round_is_not_counted(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        reset_review(self.fc)
        open_review_round(self.fc)
        review = FutureCourseSerializer(self.fc).data['section_display']['review']
        self.assertEqual(review['round'], 2)
        self.assertEqual(review['decided'], 0)

    def test_reviewers_list_reports_name_role_decision_date_comment(self):
        a = self._reviewer('a@x.com', role='Faculty')
        a.first_name, a.last_name = 'Ann', 'Adams'
        a.save()
        self._reviewer('d@x.com', role='Faculty')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved', comment='Looks fine')
        review = FutureCourseSerializer(self.fc).data['section_display']['review']

        self.assertEqual(len(review['reviewers']), 2)
        first = review['reviewers'][0]
        self.assertEqual(first['name'], 'Ann Adams')
        self.assertEqual(first['role'], 'Faculty')
        self.assertEqual(first['decision'], 'Approved')
        self.assertEqual(first['comment'], 'Looks fine')
        self.assertNotEqual(first['decided_on'], '')

        second = review['reviewers'][1]
        self.assertEqual(second['name'], 'd@x.com')
        self.assertEqual(second['decision'], '')
        self.assertEqual(second['decided_on'], '')
        self.assertEqual(second['comment'], '')

    def test_reviewers_decision_code_is_raw_for_all_three_states(self):
        a = self._reviewer('a@x.com')
        b = self._reviewer('b@x.com')
        self._reviewer('c@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        record_decision(self.fc, b, decision='not_approved')
        review = FutureCourseSerializer(self.fc).data['section_display']['review']
        codes = {r['name']: r['decision_code'] for r in review['reviewers']}
        self.assertEqual(codes, {
            'a@x.com': 'approved',
            'b@x.com': 'not_approved',
            'c@x.com': '',
        })

    def test_reviewers_ordered_by_created_on_matching_csv_export(self):
        a = self._reviewer('a@x.com')
        b = self._reviewer('b@x.com')
        open_review_round(self.fc)
        review = FutureCourseSerializer(self.fc).data['section_display']['review']
        names = [r['name'] for r in review['reviewers']]
        self.assertEqual(names, ['a@x.com', 'b@x.com'])
