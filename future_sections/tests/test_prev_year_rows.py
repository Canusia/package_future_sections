"""One pre-populated row per previous-year section, not one per term.

A teacher who taught the same course twice in a term used to get a single
row, while the "Previous Year" column beside it counted both — the two
numbers disagreed by design, and the admin had to notice and re-add the rest
by hand. Each section now gets its own row, carrying enough of the prior
section to tell the rows apart, and only for the fields the tenant actually
shows.
"""
import json

from django.contrib.auth.models import Group
from django.test import TestCase

from cis.models.course import Cohort, Course
from cis.models.customuser import CustomUser
from cis.models.district import District
from cis.models.highschool import HighSchool
from cis.models.section import ClassSection
from cis.models.settings import Setting
from cis.models.teacher import (
    Teacher, TeacherCourseCertificate, TeacherHighSchool,
)
from cis.models.term import AcademicYear, Term

from ..utils import build_initial_from_prev_year


class PrevYearRowPerSectionTests(TestCase):

    def setUp(self):
        Group.objects.get_or_create(name='faculty')
        Group.objects.get_or_create(name='instructor')

        self.prev_ay = AcademicYear.objects.create(name='2026-2027')
        self.next_ay = AcademicYear.objects.create(name='2027-2028')
        self.prev_spring = Term.objects.create(
            code='202650', label='Spring Credit 2026',
            academic_year=self.prev_ay)
        self.prev_fall = Term.objects.create(
            code='202640', label='Fall Credit 2026',
            academic_year=self.prev_ay)
        self.next_spring = Term.objects.create(
            code='202750', label='Spring Credit 2027',
            academic_year=self.next_ay)

        cohort = Cohort.objects.create(designator='CRM', name='Criminal')
        self.course = Course.objects.create(
            cohort=cohort, catalog_number='120',
            title='Criminal Investigation', name='CRM 120',
            credit_hours=3, status='Active')
        district = District.objects.create(name='D')
        self.hs = HighSchool.objects.create(
            name='Guilford High School', district=district)

        user = CustomUser.objects.create(
            username='g@x.com', email='g@x.com',
            first_name='Gabe', last_name='Ross')
        self.teacher = Teacher.objects.create(user=user)
        ths = TeacherHighSchool.objects.create(
            teacher=self.teacher, highschool=self.hs)
        self.cert = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=self.course, status='Teaching')

    def _configure(self, visible_fields=('term', 'section_number')):
        Setting.objects.update_or_create(
            key='cis_future_sections',
            defaults={'value': {
                'previous_academic_year': str(self.prev_ay.id),
                'term_mapping': json.dumps({
                    str(self.prev_spring.id): str(self.next_spring.id),
                    str(self.prev_fall.id): str(self.next_spring.id),
                }),
                'teaching_form_config': json.dumps(
                    {'fields': list(visible_fields)}),
            }},
        )

    def _section(self, section_number, term=None, **kwargs):
        return ClassSection.objects.create(
            class_number=f'C{section_number}',
            section_number=section_number,
            teacher=self.teacher, course=self.course,
            term=term or self.prev_spring, highschool=self.hs, status='A',
            **kwargs,
        )

    def test_two_sections_in_one_term_give_two_rows(self):
        self._section('DC030')
        self._section('DC040')
        self._configure()
        rows = build_initial_from_prev_year(self.cert)
        self.assertEqual(len(rows), 2)

    def test_both_rows_carry_the_mapped_term(self):
        self._section('DC030')
        self._section('DC040')
        self._configure()
        rows = build_initial_from_prev_year(self.cert)
        self.assertEqual(
            [r['term'] for r in rows],
            [str(self.next_spring.id)] * 2)

    def test_rows_are_told_apart_by_section_number(self):
        self._section('DC040')
        self._section('DC030')
        self._configure()
        rows = build_initial_from_prev_year(self.cert)
        self.assertEqual(
            [r['section_number'] for r in rows], ['DC030', 'DC040'])

    def test_ordering_is_stable_across_terms_then_sections(self):
        self._section('DC040')
        self._section('DC030')
        self._section('DC010', term=self.prev_fall)
        self._configure()
        rows = build_initial_from_prev_year(self.cert)
        # term__code ascending (Fall 202640 before Spring 202650), then
        # section_number.
        self.assertEqual(
            [r['section_number'] for r in rows],
            ['DC010', 'DC030', 'DC040'])

    def test_a_hidden_field_is_not_pre_filled(self):
        # Copying prior-year data into a field the tenant does not show would
        # store it invisibly.
        self._section('DC030', period_time='3rd')
        self._configure(visible_fields=('term',))
        rows = build_initial_from_prev_year(self.cert)
        self.assertNotIn('section_number', rows[0])
        self.assertNotIn('class_period', rows[0])

    def test_location_is_never_copied(self):
        # ClassSection.location is a FK to the SIS Location table; the form's
        # location select holds strings from the location_options setting.
        self._section('DC030')
        self._configure(visible_fields=('term', 'section_number', 'location'))
        self.assertNotIn('location', build_initial_from_prev_year(self.cert)[0])

    def test_visible_section_details_are_pre_filled(self):
        self._section('DC030', period_time='3rd', instruction_mode='DCR')
        self._configure(visible_fields=(
            'term', 'section_number', 'class_period',
            'instruction_mode', 'highschool_course_name'))
        row = build_initial_from_prev_year(self.cert)[0]
        self.assertEqual(row['class_period'], '3rd')
        self.assertEqual(row['instruction_mode'], 'DCR')

    def test_highschool_course_name_is_still_pre_filled(self):
        self._section('DC030', highschool_course_name='Intro to CJ')
        self._configure(visible_fields=('term', 'highschool_course_name'))
        row = build_initial_from_prev_year(self.cert)[0]
        self.assertEqual(row['highschool_course_name'], 'Intro to CJ')

    def test_one_section_per_term_is_unchanged(self):
        self._section('DC030')
        self._section('DC010', term=self.prev_fall)
        self._configure()
        rows = build_initial_from_prev_year(self.cert)
        self.assertEqual(len(rows), 2)
