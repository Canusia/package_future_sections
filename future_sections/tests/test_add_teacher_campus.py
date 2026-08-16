from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.test import TestCase, RequestFactory

from cis.models.customuser import CustomUser
from cis.models.course import Course, Campus, Cohort
from cis.models.term import AcademicYear

from future_sections.future_sections.utils import addable_courses_for_user

try:
    from django_login_history.models import post_login as _login_history_post_login
except Exception:
    _login_history_post_login = None


def _hs_admin_user():
    Group.objects.get_or_create(name='highschool_admin')
    u = CustomUser.objects.create(
        username='hsa@x.com', email='hsa@x.com', is_active=True)
    u.groups.add(Group.objects.get(name='highschool_admin'))
    return u


class AddableCoursesForUserTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _hs_admin_user()
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus_a = Campus.objects.create(name='Alpha', code='A')
        cls.campus_b = Campus.objects.create(name='Bravo', code='B')

        cls.a_active = Course.objects.create(
            name='A1', title='Alpha Active', cohort=cls.cohort,
            catalog_number='101', credit_hours=3, campus=cls.campus_a,
            status='Active')
        cls.a_inactive = Course.objects.create(
            name='A2', title='Alpha Inactive', cohort=cls.cohort,
            catalog_number='102', credit_hours=3, campus=cls.campus_a,
            status='Inactive')
        cls.b_active = Course.objects.create(
            name='B1', title='Bravo Active', cohort=cls.cohort,
            catalog_number='103', credit_hours=3, campus=cls.campus_b,
            status='Active')

    def _request(self):
        req = RequestFactory().get('/')
        req.user = self.user
        return req

    def test_campus_scopes_to_active_courses_in_that_campus(self):
        titles = [c.title for c in addable_courses_for_user(
            self._request(), self.ay, 'pathways', self.campus_a)]
        self.assertEqual(titles, ['Alpha Active'])

    def test_other_campus_returns_its_own_courses(self):
        titles = [c.title for c in addable_courses_for_user(
            self._request(), self.ay, 'pathways', self.campus_b)]
        self.assertEqual(titles, ['Bravo Active'])

    def test_no_campus_returns_all_active_across_campuses(self):
        titles = sorted(c.title for c in addable_courses_for_user(
            self._request(), self.ay, 'pathways', None))
        self.assertEqual(titles, ['Alpha Active', 'Bravo Active'])


class CampusFieldOrderingTests(TestCase):
    def test_campus_placed_immediately_before_course(self):
        from collections import OrderedDict
        from future_sections.future_sections.forms import AddNewTeacherForm

        form = AddNewTeacherForm.__new__(AddNewTeacherForm)
        form.fields = OrderedDict([
            ('highschool', object()),
            ('course', object()),
            ('term', object()),
            ('campus', object()),
        ])
        form._order_campus_before_course()
        keys = list(form.fields.keys())
        self.assertEqual(keys, ['highschool', 'campus', 'course', 'term'])


class AddTeacherCoursesEndpointTests(TestCase):
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
        cls.user = _hs_admin_user()
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.cohort = Cohort.objects.create(name='Co', designator='CO')
        cls.campus_a = Campus.objects.create(name='Alpha', code='A')
        cls.campus_b = Campus.objects.create(name='Bravo', code='B')
        Course.objects.create(
            name='A1', title='Alpha Active', cohort=cls.cohort,
            catalog_number='101', credit_hours=3, campus=cls.campus_a,
            status='Active')
        Course.objects.create(
            name='B1', title='Bravo Active', cohort=cls.cohort,
            catalog_number='103', credit_hours=3, campus=cls.campus_b,
            status='Active')
        cls.url = '/highschool_admin/future_sections/api/actions/add-teacher-courses/'

    def setUp(self):
        self.client.force_login(self.user)

    def test_returns_campus_scoped_courses(self):
        resp = self.client.get(self.url, {
            'academic_year_id': str(self.ay.id),
            'course_type': 'pathways',
            'campus': str(self.campus_a.id),
        })
        self.assertEqual(resp.status_code, 200)
        titles = [c['title'] for c in resp.json()['courses']]
        self.assertEqual(titles, ['Alpha Active'])

    def test_requires_academic_year_id(self):
        resp = self.client.get(self.url, {'campus': str(self.campus_a.id)})
        self.assertEqual(resp.status_code, 400)


class AddableCoursesAvailabilityRuleTests(TestCase):
    """Mirrors instructor_app's rule: active, not explicitly No, campus or null.

    `available_for_si` is unset on most rows, and the two kinds of unset (meta
    NULL, and meta dict without the key) behave oppositely under exclude() —
    both are pinned here.
    """

    def setUp(self):
        from cis.models.course import Campus
        self.campus = Campus.objects.create(name='Main', code='M')
        self.other = Campus.objects.create(name='Other', code='O')

    def _request(self):
        """A CE-staff-ish request: neither HS admin nor instructor, so no
        certificate scoping is applied and the rule is what we measure."""
        from unittest.mock import MagicMock
        from django.contrib.auth.models import Group

        from cis.models.customuser import CustomUser
        Group.objects.get_or_create(name='ce')
        user, _ = CustomUser.objects.get_or_create(
            username='ce@x.com', defaults={'email': 'ce@x.com'})
        request = MagicMock()
        request.user = user
        return request

    def _course(self, catalog, campus=None, meta='unset'):
        from cis.models.course import Cohort, Course
        if meta == 'unset':
            meta_value = {'some_other_key': 'x'}
        elif meta is None:
            meta_value = None
        else:
            meta_value = {'available_for_si': meta}
        return Course.objects.create(
            name=f'ENGL& {catalog}', status='active', title=f'Course {catalog}',
            catalog_number=catalog, campus=campus,
            cohort=Cohort.objects.create(name=catalog, designator=f'C{catalog}&'),
            meta=meta_value,
        )

    def _addable(self, campus=None):
        from future_sections.future_sections.utils import addable_courses_for_user
        return addable_courses_for_user(self._request(), None, None, campus)

    def test_includes_course_whose_meta_dict_lacks_the_key(self):
        course = self._course('101', campus=self.campus)
        self.assertIn(course, self._addable(self.campus))

    def test_includes_course_whose_meta_is_null_entirely(self):
        course = self._course('102', campus=self.campus, meta=None)
        self.assertIn(course, self._addable(self.campus))

    def test_excludes_course_explicitly_marked_no(self):
        course = self._course('103', campus=self.campus, meta='2')
        self.assertNotIn(course, self._addable(self.campus))

    def test_campusless_course_is_addable_under_any_campus(self):
        course = self._course('104', campus=None)
        self.assertIn(course, self._addable(self.campus))
        self.assertIn(course, self._addable(self.other))

    def test_campus_scoping_still_excludes_other_campuses(self):
        course = self._course('105', campus=self.other)
        self.assertNotIn(course, self._addable(self.campus))
