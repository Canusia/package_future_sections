from django.test import TestCase
from django.contrib.auth.models import Group

from cis.models.customuser import CustomUser
from cis.models.course import Course, CourseAdministrator, Cohort

from future_sections.future_sections.review.forms import SectionRequestReviewForm


def _course():
    Group.objects.get_or_create(name='faculty')
    cohort = Cohort.objects.create(designator='ENG', name='English')
    return Course.objects.create(
        cohort=cohort, catalog_number='101', title='Comp I',
        name='ENG 101', credit_hours=3, status='Active',
    )


class SectionRequestReviewFormTests(TestCase):
    def test_approved_with_existing_mentor_for_role_passes(self):
        course = _course()
        u = CustomUser.objects.create(
            username='m@x.com', email='m@x.com',
            first_name='M', last_name='X')
        ca = CourseAdministrator.objects.create(
            course=course, user=u, role='Dept. Chair', status='Active')
        form = SectionRequestReviewForm(
            data={'decision': 'approved', 'comment': '', 'existing_mentor': str(ca.id)},
            course=course, mentor_role='Dept. Chair', require_mentor=True,
        )
        self.assertTrue(form.is_valid(), msg=form.errors)
        self.assertEqual(form.cleaned_data['existing_mentor'], ca)

    def test_approved_without_mentor_when_assignment_disabled_passes(self):
        course = _course()
        form = SectionRequestReviewForm(
            data={'decision': 'approved', 'comment': ''},
            course=course, mentor_role='Faculty', require_mentor=False,
        )
        self.assertTrue(form.is_valid(), msg=form.errors)

    def test_existing_mentor_queryset_filtered_by_role(self):
        course = _course()
        u_fac = CustomUser.objects.create(
            username='f@x.com', email='f@x.com', first_name='F', last_name='X')
        u_dean = CustomUser.objects.create(
            username='d@x.com', email='d@x.com', first_name='D', last_name='X')
        CourseAdministrator.objects.create(
            course=course, user=u_fac, role='Faculty', status='Active')
        ca_dean = CourseAdministrator.objects.create(
            course=course, user=u_dean, role='Dean', status='Active')
        form = SectionRequestReviewForm(
            course=course, mentor_role='Dean', require_mentor=True)
        qs = list(form.fields['existing_mentor'].queryset)
        self.assertEqual(qs, [ca_dean])

    def test_approved_no_existing_options_requires_new_mentor(self):
        course = _course()
        form = SectionRequestReviewForm(
            data={'decision': 'approved', 'comment': ''},
            course=course, mentor_role='Faculty', require_mentor=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('new_mentor_name', form.errors)
        self.assertIn('new_mentor_email', form.errors)
