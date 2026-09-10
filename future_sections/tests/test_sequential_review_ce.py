"""CE's half of sequential review: the payload, the filter, the export and
the Notify next stage gesture."""
import json

from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.test import TestCase
from django.urls import reverse

from cis.models.course import Campus, Cohort, Course, CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.highschool import HighSchool
from cis.models.settings import Setting
from cis.models.teacher import (
    Teacher, TeacherCourseCertificate, TeacherHighSchool,
)
from cis.models.term import AcademicYear

from ..models import FutureCourse
from ..review.helpers import open_review_round, record_decision
from ..serializers import FutureCourseSerializer


def _user(email, **extra):
    return CustomUser.objects.create(
        username=email, email=email, first_name='F', last_name='L', **extra)


def _safe_force_login(client, user):
    # django_login_history's post_login handler blows up under the test
    # client (no real REMOTE_ADDR); same workaround as
    # test_send_review_reminder.py.
    from django_login_history.models import post_login
    user_logged_in.disconnect(post_login)
    try:
        client.force_login(user)
    finally:
        user_logged_in.connect(post_login)


SETTINGS = {
    'require_review': '1',
    'reviewer_roles': ['Faculty', 'Dean'],
    'reviewer_role_config': '{"Faculty": 1, "Dean": 2}',
    'review_notification_subject': 'Turn',
    'review_notification_message': 'Hi {{reviewer_first_name}} {{link}}',
    'review_escalation_recipients': '',
}


class _CEFixture(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Main', code='M')
        cls.course = Course.objects.create(
            name='A1', title='Alpha', cohort=cls.cohort, catalog_number='101',
            credit_hours=3, campus=cls.campus, status='Active')
        Group.objects.get_or_create(name='instructor')
        Group.objects.get_or_create(name='ce')
        cls.hs = HighSchool.objects.create(name='Test HS')
        teacher = Teacher.objects.create(user=_user('t@x.com'))
        ths = TeacherHighSchool.objects.create(
            teacher=teacher, highschool=cls.hs)
        cls.tc = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=cls.course, status='Applicant')

    def setUp(self):
        Setting.objects.create(key='cis_future_sections', value=dict(SETTINGS))
        self.fc = FutureCourse.objects.create(
            academic_year=self.ay, teacher_course=self.tc, status='submitted')

    def _reviewer(self, email, role='Faculty'):
        user = _user(email)
        CourseAdministrator.objects.create(
            course=self.course, user=user, role=role, status='Active')
        return user

    def _ce_user(self):
        user = _user('ce@x.com', is_staff=True)
        user.groups.add(Group.objects.get(name='ce'))
        return user


class ReviewPayloadTests(_CEFixture):

    def _summary(self):
        self.fc.refresh_from_db()
        return FutureCourseSerializer(self.fc).data[
            'section_display']['review']

    def test_the_payload_names_the_current_stage(self):
        self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        self.assertEqual(self._summary()['stage'], 1)
        self.assertFalse(self._summary()['paused'])

    def test_each_reviewer_carries_its_weight_and_turn_flag(self):
        self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        by_weight = {r['weight']: r for r in self._summary()['reviewers']}
        self.assertTrue(by_weight[1]['is_current_stage'])
        self.assertFalse(by_weight[2]['is_current_stage'])

    def test_a_denial_shows_as_paused(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')
        summary = self._summary()
        self.assertTrue(summary['paused'])
        self.assertEqual(summary['not_approved'], 1)


class PausedFilterTests(_CEFixture):

    def test_the_paused_filter_matches_only_paused_requests(self):
        # The brief names a `FutureCourseViewSet`, but the paused filter
        # actually lives on `FutureClassSectionViewSet` -- adapted here.
        from ..views.ce_api import FutureClassSectionViewSet

        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)

        other = FutureCourse.objects.create(
            academic_year=self.ay, status='pending_review')

        record_decision(self.fc, fac, decision='not_approved')

        from django.test import RequestFactory
        request = RequestFactory().get(
            '/?faculty_review=paused&academic_year=')
        request.user = self._ce_user()
        viewset = FutureClassSectionViewSet()
        viewset.request = request
        viewset.kwargs = {}
        ids = set(viewset.get_queryset().values_list('id', flat=True))
        self.assertIn(self.fc.id, ids)
        self.assertNotIn(other.id, ids)


class NotifyNextStageActionTests(_CEFixture):

    def _post_action(self):
        _safe_force_login(self.client, self._ce_user())
        return self.client.get(
            reverse('future_sections_ce:bulk_actions'),
            {'action': 'notify_next_stage', 'ids[]': [str(self.fc.id)]})

    def test_it_clears_the_pause_and_opens_the_next_stage(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')

        response = self._post_action()
        self.assertEqual(response.status_code, 200)
        self.fc.refresh_from_db()
        self.assertFalse(self.fc.is_review_paused)
        self.assertEqual(self.fc.status, 'pending_review')

    def test_a_request_that_is_not_paused_is_skipped_and_named(self):
        self._reviewer('fac@x.com', role='Faculty')
        open_review_round(self.fc)
        response = self._post_action()
        body = json.loads(response.content)
        self.assertIn('Alpha', body['message'])
        self.fc.refresh_from_db()
        self.assertFalse(self.fc.is_review_paused)

    def test_the_denial_survives_the_advance(self):
        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')
        self._post_action()
        self.assertEqual(
            self.fc.reviews.get(reviewer=fac).decision, 'not_approved')


class ExportTests(_CEFixture):

    def test_the_export_reports_the_stage_and_the_pause(self):
        from ..reports.future_classes import _faculty_review_cells

        fac = self._reviewer('fac@x.com', role='Faculty')
        self._reviewer('dean@x.com', role='Dean')
        open_review_round(self.fc)
        record_decision(self.fc, fac, decision='not_approved')

        self.fc.refresh_from_db()
        cells = _faculty_review_cells(self.fc)
        self.assertEqual(len(cells), 8)
        # A denial does not retreat the stage pointer: current_stage() is
        # the lowest UNDECIDED weight, and after Faculty (weight 1) denies,
        # the only undecided row left is Dean's at weight 2.
        self.assertEqual(cells[1], '2')     # current stage
        self.assertEqual(cells[2], 'Yes')   # paused

    def test_an_unreviewed_record_still_returns_the_full_width(self):
        from ..reports.future_classes import _faculty_review_cells

        self.assertEqual(len(_faculty_review_cells(self.fc)), 8)
