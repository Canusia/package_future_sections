"""Copying last year's sections into the formset honours the configured
class statuses, rather than assuming 'A'.

Same rule as the "Previous Year" column: the statuses come from the
`prev_year_class_status` setting, and an empty selection means every status
counts. The two must agree — a tenant seeing a course in the Previous Year
column should get that course copied when they open it.
"""

import json

from django.test import TestCase

from cis.models.customuser import CustomUser
from cis.models.course import Course, Cohort
from cis.models.district import District
from cis.models.highschool import HighSchool
from cis.models.section import ClassSection
from cis.models.settings import Setting
from cis.models.teacher import (
    Teacher, TeacherHighSchool, TeacherCourseCertificate,
)
from cis.models.term import AcademicYear, Term

from ..utils import build_initial_from_prev_year


class PrevYearCopyStatusTests(TestCase):
    def setUp(self):
        # Creating a Teacher attaches the user to these groups.
        from django.contrib.auth.models import Group
        Group.objects.get_or_create(name='faculty')
        Group.objects.get_or_create(name='instructor')

        self.prev_ay = AcademicYear.objects.create(name='2026-2027')
        self.next_ay = AcademicYear.objects.create(name='2027-2028')
        self.prev_fall = Term.objects.create(
            code='202640', label='Fall CiHS Trimester 202640',
            academic_year=self.prev_ay)
        self.prev_spring = Term.objects.create(
            code='202650', label='Spring 202650', academic_year=self.prev_ay)
        self.next_fall = Term.objects.create(
            code='202740', label='Fall CiHS Trimester 202740',
            academic_year=self.next_ay)

        cohort = Cohort.objects.create(designator='PE', name='Phys Ed')
        self.course = Course.objects.create(
            cohort=cohort, catalog_number='125', title='Phys Ed 125',
            name='PHED 125', credit_hours=3, status='Active')
        district = District.objects.create(name='D')
        self.hs = HighSchool.objects.create(
            name='Zillah High School', district=district)

        user = CustomUser.objects.create(
            username='k@x.com', email='k@x.com',
            first_name='Kekoa', last_name='Gabriel')
        self.teacher = Teacher.objects.create(user=user)
        ths = TeacherHighSchool.objects.create(
            teacher=self.teacher, highschool=self.hs)
        self.cert = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=self.course, status='Teaching')

    def _configure(self, statuses=None, mapping=True):
        term_mapping = (
            {str(self.prev_fall.id): str(self.next_fall.id),
             str(self.prev_spring.id): str(self.next_fall.id)}
            if mapping else {}
        )
        value = {
            'previous_academic_year': str(self.prev_ay.id),
            'term_mapping': json.dumps(term_mapping),
        }
        if statuses is not None:
            value['prev_year_class_status'] = statuses
        Setting.objects.update_or_create(
            key='cis_future_sections', defaults={'value': value})

    def _section(self, number, term=None, status='A'):
        return ClassSection.objects.create(
            class_number=number, section_number='A',
            teacher=self.teacher, course=self.course,
            term=term or self.prev_fall, highschool=self.hs, status=status,
        )

    def test_only_the_selected_status_is_copied(self):
        self._section('1001', status='A')
        self._section('2001', term=self.prev_spring, status='C')
        self._configure(statuses=['A'])
        rows = build_initial_from_prev_year(self.cert)
        self.assertEqual(len(rows), 1)

    def test_a_different_status_can_be_selected_instead(self):
        self._section('1001', status='A')
        self._section('2001', term=self.prev_spring, status='C')
        self._configure(statuses=['C'])
        rows = build_initial_from_prev_year(self.cert)
        self.assertEqual(len(rows), 1)

    def test_several_statuses_can_be_selected_together(self):
        self._section('1001', status='A')
        self._section('2001', term=self.prev_spring, status='C')
        self._configure(statuses=['A', 'C'])
        rows = build_initial_from_prev_year(self.cert)
        self.assertEqual(len(rows), 2)

    def test_empty_selection_copies_every_status(self):
        self._section('1001', status='A')
        self._section('2001', term=self.prev_spring, status='C')
        for unset in ([], None):
            self._configure(statuses=unset)
            rows = build_initial_from_prev_year(self.cert)
            self.assertEqual(len(rows), 2, unset)

    def test_status_not_present_in_the_data_copies_nothing(self):
        self._section('1001', status='A')
        self._configure(statuses=['C'])
        self.assertEqual(build_initial_from_prev_year(self.cert), [])

    def test_term_mapping_is_still_required(self):
        # Unchanged behaviour: no mapping configured means no copy at all,
        # whatever the status selection says.
        self._section('1001', status='A')
        self._configure(statuses=['A'], mapping=False)
        self.assertEqual(build_initial_from_prev_year(self.cert), [])

    def test_mapped_term_is_carried_into_the_row(self):
        self._section('1001', status='A')
        self._configure(statuses=['A'])
        rows = build_initial_from_prev_year(self.cert)
        self.assertEqual(rows[0]['term'], str(self.next_fall.id))
