import json

from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from rest_framework.exceptions import PermissionDenied

from cis.models.course import Campus, Cohort, Course
from cis.models.customuser import CustomUser
from cis.models.highschool import HighSchool
from cis.models.highschool_administrator import (
    HSAdministrator, HSAdministratorPosition, HSPosition,
)
from cis.models.settings import Setting
from cis.models.term import AcademicYear, Term

from ..forms import AddNewTeacherForm
from ..models import FutureCourse
from ..utils import assert_editable


class AssertEditableTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        Group.objects.get_or_create(name='highschool_admin')
        Group.objects.get_or_create(name='ce')
        cls.ay = AcademicYear.objects.create(name='2099-2100')

        cls.hs_admin = CustomUser.objects.create(
            username='hsa@x.com', email='hsa@x.com', is_active=True)
        cls.hs_admin.groups.add(Group.objects.get(name='highschool_admin'))
        hs = HighSchool.objects.create(name='Test HS')
        position = HSPosition.objects.create(name='Coordinator')
        admin = HSAdministrator.objects.create(user=cls.hs_admin)
        HSAdministratorPosition.objects.create(
            hsadmin=admin, highschool=hs, position=position, status='Active')

        cls.ce_user = CustomUser.objects.create(
            username='ce@x.com', email='ce@x.com', is_active=True)
        cls.ce_user.groups.add(Group.objects.get(name='ce'))

    def _request(self, user):
        req = RequestFactory().post('/')
        req.user = user
        return req

    def _fc(self, status):
        return FutureCourse.objects.create(
            academic_year=self.ay, status=status)

    def test_submitted_is_editable_by_the_school(self):
        assert_editable(self._fc('submitted'), self._request(self.hs_admin))

    def test_pending_review_is_refused_for_the_school(self):
        with self.assertRaises(PermissionDenied):
            assert_editable(
                self._fc('pending_review'), self._request(self.hs_admin))

    def test_reviewed_is_refused_for_the_school(self):
        with self.assertRaises(PermissionDenied):
            assert_editable(
                self._fc('reviewed'), self._request(self.hs_admin))

    def test_ce_is_never_locked_out(self):
        for status in ('submitted', 'pending_review', 'reviewed'):
            assert_editable(self._fc(status), self._request(self.ce_user))


class AddTeacherRespectsTheLockTests(TestCase):
    """add-teacher appends to an existing record through get_or_add, so it
    must not be able to grow one that is locked."""

    @classmethod
    def setUpTestData(cls):
        Group.objects.get_or_create(name='instructor')
        Group.objects.get_or_create(name='highschool_admin')
        cls.user = CustomUser.objects.create(
            username='hsa-lock@x.com', email='hsa-lock@x.com', is_active=True)
        cls.user.groups.add(Group.objects.get(name='highschool_admin'))

        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.term = Term.objects.create(
            label='Fall 2099', code='F99', academic_year=cls.ay)
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus = Campus.objects.create(name='Stocked', code='S')
        cls.course = Course.objects.create(
            name='A1', title='Alpha Active', cohort=cls.cohort,
            catalog_number='101', credit_hours=3, campus=cls.campus,
            status='Active')

        cls.highschool = HighSchool.objects.create(name='Test HS')
        position = HSPosition.objects.create(name='Coordinator')
        hsadmin = HSAdministrator.objects.create(user=cls.user)
        HSAdministratorPosition.objects.create(
            hsadmin=hsadmin, highschool=cls.highschool, position=position,
            status='Active')

    def setUp(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={'academic_year': str(self.ay.id),
                   'teaching_form_config': json.dumps({'fields': ['term']}),
                   'add_teacher_form_config': json.dumps({'fields': []})})

    def _submit(self, teacher=None):
        req = RequestFactory().post('/')
        req.user = self.user
        data = {
            'action': 'add_new_teacher',
            'academic_year_id': str(self.ay.id),
            'highschool': str(self.highschool.id),
            'term': str(self.term.id),
            'course': str(self.course.id),
        }
        if teacher is not None:
            # Re-selecting the existing teacher, as a real repeat submission
            # would through the dropdown. Re-sending the raw name/email trio
            # instead would re-hit `Teacher.get_or_add`, which dedupes on
            # `secondary_email` rather than the primary email this form
            # collects — a pre-existing cis bug, unrelated to the lock this
            # test is checking, that would otherwise make the second
            # submission fail before it ever reaches `FutureCourse`.
            data['teacher'] = str(teacher.id)
        else:
            data['teacher_first_name'] = 'Mike'
            data['teacher_last_name'] = 'Moeller'
            data['teacher_email'] = 'moeller@example.com'
        form = AddNewTeacherForm(req, self.ay, 'pathways', data=data)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        return form.save(req, self.ay)

    def test_first_submission_succeeds_and_leaves_it_submitted(self):
        record = self._submit()
        self.assertEqual(record.status, 'submitted')

    def test_appending_to_a_locked_record_is_refused(self):
        record = self._submit()
        teacher = record.teacher_course.teacher_highschool.teacher
        record.status = 'pending_review'
        record.save(update_fields=['status'])
        with self.assertRaises(PermissionDenied):
            self._submit(teacher=teacher)
