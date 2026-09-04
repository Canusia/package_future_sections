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
from ..review.helpers import open_review_round, record_decision, reset_review


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
    # Visibility is now gated by holding a review row, not just an Active
    # CourseAdministrator row — open the round so the reviewer has one.
    open_review_round(fc)
    return reviewer, fc


def _world_multi(emails, reviewer_role='Faculty'):
    """Like `_world`, but snapshots a round with one reviewer per email."""
    Group.objects.get_or_create(name='faculty')
    Group.objects.get_or_create(name='instructor')
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
    reviewers = []
    for email in emails:
        u = CustomUser.objects.create(username=email, email=email)
        CourseAdministrator.objects.create(
            course=course, user=u, role=reviewer_role, status='Active')
        reviewers.append(u)
    Setting.objects.create(
        key='cis_future_sections',
        value={'reviewer_roles': [reviewer_role], 'require_review': 'Yes'},
    )
    open_review_round(fc)
    return reviewers, fc, course


def _faculty_review_status(fc, user, tab='pending'):
    factory = APIRequestFactory()
    req = factory.get('/api/section_request/', {'tab': tab})
    force_authenticate(req, user=user)
    view = SectionRequestViewSet.as_view({'get': 'list'})
    resp = view(req)
    rows = resp.data['results'] if isinstance(resp.data, dict) else resp.data
    row = next(r for r in rows if r['id'] == str(fc.id))
    return row['faculty_review_status']


class FacultyReviewStatusTests(TestCase):
    """`faculty_review_status` is the *current* reviewer's own decision,
    not a whole-round summary — see review/api.py."""

    def test_a_decided_request_shows_the_reviewers_own_decision(self):
        [a], fc, _course = _world_multi(['a@x.com'])
        record_decision(fc, a, decision='approved', comment='')
        status = _faculty_review_status(fc, a, tab='reviewed')
        self.assertTrue(status.startswith('Approved'))

    def test_a_second_reviewer_sees_their_own_decision_not_the_first(self):
        [a, b], fc, _course = _world_multi(['a@x.com', 'b@x.com'])
        record_decision(fc, a, decision='approved', comment='')
        record_decision(fc, b, decision='not_approved', comment='')
        self.assertTrue(
            _faculty_review_status(fc, a, tab='reviewed').startswith('Approved'))
        self.assertEqual(
            _faculty_review_status(fc, b, tab='reviewed'), 'Not Approved')

    def test_an_undecided_reviewer_sees_pending(self):
        [a], fc, _course = _world_multi(['a@x.com'])
        status = _faculty_review_status(fc, a, tab='pending')
        self.assertEqual(status, 'Pending')

    def test_pending_tab_does_not_show_a_stale_prior_round_decision(self):
        # Round 1: reviewer `a` decides, is reset by CE, round 2 opens with
        # a fresh (undecided) slot for `a`. The Pending tab should show
        # Pending, not their round-1 "Approved".
        [a], fc, _course = _world_multi(['a@x.com'])
        record_decision(fc, a, decision='approved', comment='')
        fc.refresh_from_db()
        reset_review(fc)
        self.assertEqual(open_review_round(fc), 2)
        status = _faculty_review_status(fc, a, tab='pending')
        self.assertEqual(status, 'Pending')

    def test_the_mentor_name_still_renders_escaped(self):
        [a], fc, course = _world_multi(['a@x.com'])
        mentor = CustomUser.objects.create(
            username='m@x.com', email='m@x.com',
            first_name='<b>Mal</b>', last_name='"lory"')
        record_decision(fc, a, decision='approved', comment='', mentor=mentor)
        status = _faculty_review_status(fc, a, tab='reviewed')
        self.assertIn('&lt;b&gt;Mal&lt;/b&gt;', status)
        self.assertNotIn('<b>Mal</b>', status)


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
