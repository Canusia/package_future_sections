"""Campus-scoped school picker on the add-teacher form (cis HighSchoolCampus)."""
import uuid

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings

from cis.campus_context import campus_context
from cis.models.course import Campus
from cis.models.customuser import CustomUser
from cis.models.highschool import HighSchool, HighSchoolCampus
from cis.models.highschool_administrator import (
    HSAdministrator, HSAdministratorPosition, HSPosition)
from cis.models.teacher import Teacher, TeacherHighSchool
from cis.models.term import AcademicYear


def _sfx():
    return uuid.uuid4().hex[:8]


def _campus():
    return Campus.objects.create(
        name=f'C-{_sfx()}', code=f'{settings.CAMPUS_CODE_PREFIX}_{_sfx()[:6]}')


def _hs(name, campus=None, status='Active'):
    hs = HighSchool.objects.create(name=name, code=_sfx())
    HighSchoolCampus.objects.filter(highschool=hs).delete()
    if campus is not None:
        HighSchoolCampus.objects.create(
            highschool=hs, campus=campus, status=status)
    return hs


def _user(role):
    Group.objects.get_or_create(name=role)
    u = CustomUser.objects.create(
        username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', is_active=True)
    u.groups.add(Group.objects.get(name=role))
    return u


class _Base(TestCase):
    role = 'highschool_admin'

    def setUp(self):
        self.a, self.b = _campus(), _campus()
        self.mine = _hs('Mine', self.a)
        self.foreign = _hs('Foreign', self.b)
        self.dormant = _hs('Dormant', self.a, 'Inactive')
        with campus_context(self.a):
            self.ay = AcademicYear.objects.create(
                name=f'AY-{_sfx()}', campus=self.a)
        self.user = _user(self.role)
        schools = [self.mine, self.foreign, self.dormant]
        if self.role == 'highschool_admin':
            hsadmin = HSAdministrator.objects.create(user=self.user)
            position = HSPosition.objects.create(name=f'P-{_sfx()}')
            for hs in schools:
                HSAdministratorPosition.objects.create(
                    hsadmin=hsadmin, highschool=hs, position=position,
                    status='Active')
        else:
            teacher = Teacher.objects.create(user=self.user)
            for hs in schools:
                TeacherHighSchool.objects.create(teacher=teacher, highschool=hs)

    def _form(self, data=None):
        from ..forms import AddNewTeacherForm
        req = RequestFactory().get('/')
        req.user = self.user
        return AddNewTeacherForm(req, self.ay, 'pathways', data=data)

    def _schools(self):
        return list(self._form().fields['highschool'].queryset)


class _Cases:
    @override_settings(MULTI_CAMPUS=True)
    def test_multi_campus_excludes_other_campus_and_inactive(self):
        with campus_context(self.a):
            self.assertEqual(self._schools(), [self.mine])

    @override_settings(MULTI_CAMPUS=True)
    def test_multi_campus_foreign_post_rejected(self):
        with campus_context(self.a):
            # The field itself: the form's clean() assumes a complete POST.
            field = self._form().fields['highschool']
            with self.assertRaises(ValidationError):
                field.clean(str(self.foreign.pk))
            self.assertEqual(field.clean(str(self.mine.pk)), self.mine)

    @override_settings(MULTI_CAMPUS=True)
    def test_multi_campus_is_evaluated_per_request(self):
        with campus_context(self.b):
            self.assertEqual(self._schools(), [self.foreign])

    @override_settings(MULTI_CAMPUS=False)
    def test_single_campus_offers_campus_linked_active_schools(self):
        with campus_context(self.a):
            self.assertEqual(self._schools(), [self.mine])


class HsAdminAddTeacherTests(_Cases, _Base):
    role = 'highschool_admin'


class InstructorAddTeacherTests(_Cases, _Base):
    role = 'instructor'
