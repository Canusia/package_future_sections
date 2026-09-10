from django.contrib.auth.models import Group
from django.test import TestCase

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.teacher import Teacher, TeacherCourseCertificate, TeacherHighSchool
from cis.models.highschool import HighSchool
from cis.models.term import AcademicYear

from ..models import FutureCourse
from ..reports.future_classes import _faculty_review_cells
from ..review.helpers import open_review_round, record_decision, reset_review


def _user(email, first_name=''):
    return CustomUser.objects.create(
        username=email, email=email, first_name=first_name)


class ReviewExportColumnsTests(TestCase):

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

    def _reviewer(self, email, role='Faculty', status='Active', first_name=''):
        u = _user(email, first_name=first_name)
        CourseAdministrator.objects.create(
            course=self.course, user=u, role=role, status=status)
        return u

    def test_columns_aggregate_every_reviewer(self):
        a = self._reviewer('a@x.com', first_name='Ann')
        d = self._reviewer('d@x.com', first_name='Dee')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved', comment='fine')
        record_decision(self.fc, d, decision='not_approved', comment='no')
        self.fc.refresh_from_db()
        cells = _faculty_review_cells(self.fc)
        self.assertEqual(cells[0], '1')
        # Both reviewers share weight 0 (no reviewer_role_config here) and
        # both have decided, so no undecided weight remains: stage is ''.
        # The denial pauses the request, and nothing here resumes it.
        self.assertEqual(cells[1], '')
        self.assertEqual(cells[2], 'Yes')
        self.assertIn('Ann', cells[3])
        self.assertIn('Dee', cells[3])
        self.assertEqual(cells[4], 'Approved; Not approved')
        self.assertEqual(cells[7], 'fine; no')

    def test_an_unreviewed_request_yields_empty_cells(self):
        cells = _faculty_review_cells(self.fc)
        self.assertEqual(cells, ['', '', '', '', '', '', '', ''])

    def test_partially_decided_round_keeps_reviewers_positionally_aligned(self):
        a = self._reviewer('a@x.com', first_name='Ann')
        self._reviewer('d@x.com', first_name='Dee')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved', comment='fine')
        self.fc.refresh_from_db()
        cells = _faculty_review_cells(self.fc)
        reviewers = cells[3].split('; ')
        decisions = cells[4].split('; ')
        self.assertEqual(len(reviewers), len(decisions))
        ann_index = reviewers.index('Ann')
        self.assertEqual(decisions[ann_index], 'Approved')
        dee_index = reviewers.index('Dee')
        self.assertEqual(decisions[dee_index], '')

    def test_semicolon_in_comment_is_collapsed_so_it_cannot_join_as_a_cell(self):
        a = self._reviewer('a@x.com', first_name='Ann')
        d = self._reviewer('d@x.com', first_name='Dee')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved', comment='fine; great')
        record_decision(self.fc, d, decision='not_approved', comment='no')
        self.fc.refresh_from_db()
        cells = _faculty_review_cells(self.fc)
        comments = cells[7].split('; ')
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0], 'fine, great')
        self.assertEqual(comments[1], 'no')

    def test_only_the_live_round_is_exported(self):
        a = self._reviewer('a@x.com', first_name='Ann')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='approved', comment='old')
        reset_review(self.fc)
        open_review_round(self.fc)
        self.fc.refresh_from_db()
        cells = _faculty_review_cells(self.fc)
        self.assertEqual(cells[0], '2')
        self.assertEqual(cells[7], '')

    def test_current_stage_and_paused_columns(self):
        a = self._reviewer('a@x.com', first_name='Ann')
        self._reviewer('d@x.com', first_name='Dee')
        open_review_round(self.fc)
        record_decision(self.fc, a, decision='not_approved')
        self.fc.refresh_from_db()
        cells = _faculty_review_cells(self.fc)
        # Both reviewers share weight 0, so Dee's undecided row is the
        # remaining stage.
        self.assertEqual(cells[1], '0')
        self.assertEqual(cells[2], 'Yes')
