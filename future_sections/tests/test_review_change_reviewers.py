"""CE changes to a live review round: skip, delete and add a reviewer.

A skip marks the row `skipped` and keeps it as history. A delete removes an
outstanding or skipped row outright. Either one advances the request through
`advance_or_finish` when it completes the current stage. An add inserts a
row into the live round at the current stage or later.
"""
import json

from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase, override_settings

from mailer.engine import send_all

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.settings import Setting
from cis.models.teacher import Teacher, TeacherCourseCertificate, TeacherHighSchool
from cis.models.highschool import HighSchool
from cis.models.term import AcademicYear

from ..models import FutureCourse, SectionRequestReview
from ..review.helpers import (
    NotAReviewerError, current_stage, open_review_round, record_decision,
)

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def _user(email):
    return CustomUser.objects.create(
        username=email, email=email, first_name='F', last_name=email[0])


class ChangeReviewersBase(TestCase):
    """Faculty (weight 10) → Dept. Chair (20) → Dean (30)."""

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
        Setting.objects.create(key='cis_future_sections', value={
            'require_review': '1',
            'reviewer_roles': ['Faculty', 'Dept. Chair', 'Dean'],
            'reviewer_role_config': json.dumps(
                {'Faculty': 10, 'Dept. Chair': 20, 'Dean': 30}),
            'review_notification_subject': 'Your turn',
            'review_notification_message':
                'Hi {{reviewer_first_name}} {{requests}} {{link}}',
        })
        self.fc = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=self.tc, status='submitted')
        self.staff = _user('ce@x.com')

    def _reviewer(self, email, role):
        u = _user(email)
        CourseAdministrator.objects.create(
            course=self.course, user=u, role=role, status='Active')
        return u

    def _row(self, user):
        return SectionRequestReview.objects.get(
            future_course=self.fc, reviewer=user, round=self.fc.review_round)

    def _flush_outbox(self):
        send_all()
        sent = [m.to for m in mail.outbox]
        mail.outbox = []
        return sent


class SkippedDecisionTests(ChangeReviewersBase):

    def test_skipped_is_a_labelled_decision(self):
        self.assertEqual(SectionRequestReview.SKIPPED, 'skipped')
        self.assertEqual(
            dict(SectionRequestReview.DECISION_CHOICES)['skipped'], 'Skipped')

    def test_a_skipped_reviewer_cannot_record_a_decision(self):
        faculty = self._reviewer('f@x.com', 'Faculty')
        self._reviewer('g@x.com', 'Faculty')
        open_review_round(self.fc)
        row = self._row(faculty)
        row.decision = SectionRequestReview.SKIPPED
        row.skipped_by = self.staff
        row.save()

        with self.assertRaises(NotAReviewerError):
            record_decision(self.fc, faculty, decision='approved')
        self.assertEqual(self._row(faculty).decision, 'skipped')
