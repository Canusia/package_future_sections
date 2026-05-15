from django.test import TestCase

from cis.models.customuser import CustomUser
from cis.models.course import Course, Cohort
from cis.models.term import AcademicYear, Term
from cis.models.highschool import HighSchool
from cis.models.district import District
from cis.models.teacher import (
    Teacher, TeacherHighSchool, TeacherCourseCertificate,
)
from cis.models.section import ClassSection
from cis.models.settings import Setting

from future_sections.future_sections.utils import get_lookback_universe


def _build_world():
    Group_setup()  # ensure groups exist
    ay = AcademicYear.objects.create(name='2025-2026')
    fall = Term.objects.create(code='FA25', label='Fall 2025', academic_year=ay)
    spring = Term.objects.create(code='SP26', label='Spring 2026', academic_year=ay)

    cohort = Cohort.objects.create(designator='ENG', name='English')
    course = Course.objects.create(
        cohort=cohort, catalog_number='101', title='Comp I',
        name='ENG 101', credit_hours=3, status='Active',
    )
    district = District.objects.create(name='D')
    hs = HighSchool.objects.create(name='HS', district=district)

    def make_teacher_with_cert(email, cert_status='Teaching'):
        user = CustomUser.objects.create(
            username=email, email=email,
            first_name=email[0], last_name='Teach')
        teacher = Teacher.objects.create(user=user)
        ths = TeacherHighSchool.objects.create(teacher=teacher, highschool=hs)
        cert = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=course, status=cert_status)
        return teacher, cert

    t_fall, cert_fall = make_teacher_with_cert('fall@x.com')
    t_spring, cert_spring = make_teacher_with_cert('spring@x.com')
    t_neither, cert_neither = make_teacher_with_cert('none@x.com')
    t_applicant, cert_applicant = make_teacher_with_cert(
        'app@x.com', cert_status='Applicant')

    # Active section in Fall for t_fall + course
    ClassSection.objects.create(
        teacher=t_fall, course=course, term=fall,
        highschool=hs, status='A',
        section_number='001', class_number=1001,
        start_date='2025-09-01', end_date='2025-12-15',
    )
    # Active section in Spring for t_spring + course
    ClassSection.objects.create(
        teacher=t_spring, course=course, term=spring,
        highschool=hs, status='A',
        section_number='001', class_number=1002,
        start_date='2026-01-15', end_date='2026-05-30',
    )
    # Cancelled section for t_neither (should be ignored)
    ClassSection.objects.create(
        teacher=t_neither, course=course, term=fall,
        highschool=hs, status='C',
        section_number='001', class_number=1003,
        start_date='2025-09-01', end_date='2025-12-15',
    )
    return {
        'fall': fall, 'spring': spring,
        'cert_fall': cert_fall, 'cert_spring': cert_spring,
        'cert_neither': cert_neither, 'cert_applicant': cert_applicant,
    }


def Group_setup():
    from django.contrib.auth.models import Group
    Group.objects.get_or_create(name='faculty')
    Group.objects.get_or_create(name='instructor')


class LookbackUniverseTests(TestCase):
    def test_only_active_section_teachers_included(self):
        w = _build_world()
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'lookback_terms': [str(w['fall'].id)],
                'teacher_course_status': ['Teaching'],
                'allow_new_teacher_create': '2',  # No
            },
        )
        certs = list(get_lookback_universe())
        self.assertIn(w['cert_fall'], certs)
        # Spring teacher not in lookback; cancelled-section teacher excluded
        self.assertNotIn(w['cert_spring'], certs)
        self.assertNotIn(w['cert_neither'], certs)
        # Applicant not in universe when allow_new_teacher_create='No'
        self.assertNotIn(w['cert_applicant'], certs)

    def test_multi_term_lookback(self):
        w = _build_world()
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'lookback_terms': [str(w['fall'].id), str(w['spring'].id)],
                'teacher_course_status': ['Teaching'],
                'allow_new_teacher_create': '2',
            },
        )
        certs = list(get_lookback_universe())
        self.assertIn(w['cert_fall'], certs)
        self.assertIn(w['cert_spring'], certs)
        self.assertNotIn(w['cert_neither'], certs)

    def test_applicant_carveout_when_allow_new_teacher_create_yes(self):
        w = _build_world()
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'lookback_terms': [str(w['fall'].id)],
                'teacher_course_status': ['Teaching', 'Applicant'],
                'allow_new_teacher_create': '1',  # Yes
            },
        )
        certs = list(get_lookback_universe())
        self.assertIn(w['cert_fall'], certs)
        # Applicant unioned in despite no Section history
        self.assertIn(w['cert_applicant'], certs)


class GetCourseCertificatesForUserTests(TestCase):
    def test_instructor_sees_only_their_lookback_certs(self):
        from django.contrib.auth.models import Group
        from django.test import RequestFactory
        from future_sections.future_sections.utils import get_course_certificates_for_user

        w = _build_world()
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'lookback_terms': [str(w['fall'].id)],
                'teacher_course_status': ['Teaching'],
                'course_status': ['Active'],
                'allow_new_teacher_create': '2',
            },
        )
        Group.objects.get_or_create(name='instructor')
        instructor_user = w['cert_fall'].teacher_highschool.teacher.user
        instructor_user.groups.add(Group.objects.get(name='instructor'))

        factory = RequestFactory()
        request = factory.get('/')
        request.user = instructor_user
        certs = list(get_course_certificates_for_user(request))
        self.assertIn(w['cert_fall'], certs)
        self.assertNotIn(w['cert_spring'], certs)
