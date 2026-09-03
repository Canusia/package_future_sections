"""The add-teacher form's show/hide pairs come from the schema.

`new_teacher_email` declares `depends_on: teacher_changed` exactly as
`new_teacher_name` does, but the template hardcoded a two-entry list and
left the email field permanently visible. The list is derived now, so a
new dependent field is wired up by declaring it in the schema alone.
"""
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.test import SimpleTestCase, TestCase

from cis.models.customuser import CustomUser
from cis.models.term import AcademicYear

from ..utils import dependent_field_pairs

try:
    from django_login_history.models import post_login as _login_history_post_login
except Exception:
    _login_history_post_login = None


class DependentFieldPairTests(SimpleTestCase):

    def test_new_teacher_email_is_paired_with_the_teacher_changed_toggle(self):
        self.assertIn(
            ['#id_teacher_changed', '#div_id_new_teacher_email',
             '#id_new_teacher_email'],
            dependent_field_pairs())

    def test_new_teacher_name_pairing_is_unchanged(self):
        self.assertIn(
            ['#id_teacher_changed', '#div_id_new_teacher_name',
             '#id_new_teacher_name'],
            dependent_field_pairs())

    def test_highschool_title_pairing_is_unchanged(self):
        self.assertIn(
            ['#id_highschool_title_changed', '#div_id_new_highschool_title',
             '#id_new_highschool_title'],
            dependent_field_pairs())

    def test_every_pair_names_a_declared_dependency(self):
        from ..schemas import TeachingSectionFieldSchema
        expected = {
            (parent, child)
            for child, parent in
            TeachingSectionFieldSchema.get_dependent_fields().items()
        }
        actual = {
            (p[0][len('#id_'):], p[2][len('#id_'):])
            for p in dependent_field_pairs()
        }
        self.assertEqual(actual, expected)


class AddTeacherPageWiringTests(TestCase):
    """The rendered page carries the derived pairs, not a hardcoded list."""

    @classmethod
    def setUpClass(cls):
        if _login_history_post_login is not None:
            user_logged_in.disconnect(_login_history_post_login)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if _login_history_post_login is not None:
            user_logged_in.connect(_login_history_post_login)

    @classmethod
    def setUpTestData(cls):
        Group.objects.get_or_create(name='highschool_admin')
        cls.user = CustomUser.objects.create(
            username='hsa-dep@x.com', email='hsa-dep@x.com', is_active=True)
        cls.user.groups.add(Group.objects.get(name='highschool_admin'))
        cls.ay = AcademicYear.objects.create(name='2099-2100')

    def test_page_wires_the_new_teacher_email_toggle(self):
        from cis.models.highschool import HighSchool
        from cis.models.highschool_administrator import (
            HSAdministrator, HSAdministratorPosition, HSPosition,
        )
        highschool = HighSchool.objects.create(name='Dep HS')
        position = HSPosition.objects.create(name='Coordinator')
        hsadmin = HSAdministrator.objects.create(user=self.user)
        HSAdministratorPosition.objects.create(
            hsadmin=hsadmin, highschool=highschool, position=position,
            status='Active')

        self.client.force_login(self.user)
        resp = self.client.get(
            '/highschool_admin/future_sections/api/actions/add-teacher/',
            {'academic_year_id': str(self.ay.id)})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '#div_id_new_teacher_email')
