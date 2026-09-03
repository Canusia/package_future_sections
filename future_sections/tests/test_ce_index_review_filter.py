"""CE index `faculty_review` dropdown filter.

Task 7 removed the only writer of `section_info['faculty_review']`, so the
filter that read `section_info__faculty_review__decision` was dead:
'approved'/'not_approved' matched nothing and 'pending' (an isnull check on
a key nobody ever writes) matched everything. This repoints all three
options at `SectionRequestReview` rows in the live round.

The filter matches on the *presence* of individual decisions, never an
aggregate outcome for the request — see
`test_a_request_with_both_decisions_matches_both_filters` below, which
pins that a split decision deliberately appears under both options.
"""
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
from ..review.helpers import open_review_round, record_decision, reset_review


def _user(email):
    return CustomUser.objects.create(username=email, email=email)


def _safe_force_login(client, user):
    # django_login_history's post_login signal handler blows up under the
    # test client (no real REMOTE_ADDR), unrelated to what's under test
    # here. Same workaround used in test_ce_review_actions.py.
    from django_login_history.models import post_login
    user_logged_in.disconnect(post_login)
    try:
        client.force_login(user)
    finally:
        user_logged_in.connect(post_login)


class CeIndexReviewFilterTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Main', code='M')
        cls.course = Course.objects.create(
            name='A1', title='Alpha', cohort=cls.cohort, catalog_number='101',
            credit_hours=3, campus=cls.campus, status='Active')
        for name in ('ce', 'instructor'):
            Group.objects.get_or_create(name=name)
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
        self.ce_user = CustomUser.objects.create_user(
            username='ce@x.com', email='ce@x.com', password='pw')
        self.ce_user.groups.add(Group.objects.get(name='ce'))
        _safe_force_login(self.client, self.ce_user)

    def _reviewer(self, email, role='Faculty', status='Active'):
        u = _user(email)
        CourseAdministrator.objects.create(
            course=self.course, user=u, role=role, status=status)
        return u

    def _filter(self, faculty_review):
        url = reverse('future_sections_ce:future_class_section-list')
        response = self.client.get(url, {
            'academic_year': str(self.ay.id),
            'faculty_review': faculty_review,
        })
        self.assertEqual(response.status_code, 200)
        return [row['id'] for row in response.data['results']]

    def test_a_request_with_both_decisions_matches_both_filters(self):
        a = self._reviewer('a@x.com')
        b = self._reviewer('b@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        record_decision(self.fc, b, decision='not_approved')

        self.assertIn(str(self.fc.id), self._filter('approved'))
        self.assertIn(str(self.fc.id), self._filter('not_approved'))

    def test_fully_decided_request_is_not_pending(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')

        self.assertNotIn(str(self.fc.id), self._filter('pending'))

    def test_a_request_still_awaiting_a_decision_is_pending(self):
        a = self._reviewer('a@x.com')
        self._reviewer('b@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')

        self.assertIn(str(self.fc.id), self._filter('pending'))

    def test_a_request_never_sent_for_review_matches_none_of_the_three(self):
        ids_approved = self._filter('approved')
        ids_not_approved = self._filter('not_approved')
        ids_pending = self._filter('pending')

        self.assertNotIn(str(self.fc.id), ids_approved)
        self.assertNotIn(str(self.fc.id), ids_not_approved)
        self.assertNotIn(str(self.fc.id), ids_pending)

    def test_a_previous_rounds_decision_does_not_carry_over(self):
        a = self._reviewer('a@x.com')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved')
        reset_review(self.fc)
        open_review_round(self.fc)

        self.assertNotIn(str(self.fc.id), self._filter('approved'))
