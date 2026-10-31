"""Course Information requests vs. imported SIS sections (#7)."""
import csv
import io
import uuid

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from cis.models.course import Cohort, Course
from cis.models.customuser import CustomUser
from cis.models.highschool import HighSchool
from cis.models.section import ClassSection
from cis.models.settings import Setting
from cis.models.teacher import (
    Teacher, TeacherCourseCertificate, TeacherHighSchool)
from cis.models.term import AcademicYear, Term

from ..models import FutureCourse
from ..sis_reconcile import (
    candidate_sections, link_sections, reconcile, requested_count)
from .test_email_new_teacher_send import _safe_force_login


def _sfx():
    return uuid.uuid4().hex[:6]


class RequestedCountTests(TestCase):
    def test_blank_or_missing_is_one_row_one_section(self):
        self.assertEqual(requested_count({}), 1)
        self.assertEqual(requested_count({'number_of_sections': ''}), 1)

    def test_number_of_sections_is_used(self):
        self.assertEqual(requested_count({'number_of_sections': '3'}), 3)
        self.assertEqual(requested_count({'number_of_sections': 2}), 2)

    def test_garbage_counts_as_one(self):
        self.assertEqual(requested_count({'number_of_sections': 'two'}), 1)


class _Base(TestCase):
    def setUp(self):
        for name in ('ce', 'instructor'):
            Group.objects.get_or_create(name=name)
        self.ay = AcademicYear.objects.create(name=f'AY-{_sfx()}')
        self.fall = Term.objects.create(
            academic_year=self.ay, code='FA', label='Fall')
        self.spring = Term.objects.create(
            academic_year=self.ay, code='SP', label='Spring')
        # RVC-style sub-terms the SIS imports into.
        self.fall_3l = Term.objects.create(
            academic_year=self.ay, code='FA3L', label='Fall 3L',
            parent=self.fall)
        self.spring_6l = Term.objects.create(
            academic_year=self.ay, code='SP6L', label='Spring 6L',
            parent=self.spring)
        cohort = Cohort.objects.create(designator=f'L{_sfx()}', name='Lit')
        self.course = Course.objects.create(
            cohort=cohort, catalog_number='139', title='LIT 139',
            name='LIT 139', credit_hours=3, status='Active')
        self.hs = HighSchool.objects.create(name=f'Alpha {_sfx()}')
        self.other_hs = HighSchool.objects.create(name=f'Beta {_sfx()}')
        self.teacher = Teacher.objects.create(user=CustomUser.objects.create(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com',
            first_name='T', last_name='One'))
        ths = TeacherHighSchool.objects.create(
            teacher=self.teacher, highschool=self.hs)
        self.cert = TeacherCourseCertificate.objects.create(
            teacher_highschool=ths, course=self.course, status='Teaching')
        self._n = 1000
        Setting.objects.update_or_create(
            key='cis_future_sections',
            defaults={'value': {'academic_year': str(self.ay.id)}})

    def _request(self, sections, teaching='yes', cert=None):
        return FutureCourse.objects.create(
            teacher_course=cert or self.cert, academic_year=self.ay,
            section_info={'teaching': teaching, 'sections': sections})

    def _section(self, term, hs=None, teacher=None, status='A'):
        self._n += 1
        return ClassSection.objects.create(
            course=self.course, term=term, highschool=hs or self.hs,
            teacher=teacher if teacher is not None else self.teacher,
            status=status, section_number=f'DC{self._n % 100:03d}',
            class_number=self._n)

    def _row(self, rows, term):
        match = [r for r in rows if r['term'] == term]
        self.assertEqual(len(match), 1, rows)
        return match[0]


class ReconcileTests(_Base):
    def test_fewer_imported_than_requested_needs_more(self):
        self._request([{'term': str(self.fall.id), 'number_of_sections': '3'}])
        self._section(self.fall_3l)
        self._section(self.fall_3l)
        row = self._row(reconcile(self.ay), 'Fall')
        self.assertEqual((row['requested'], row['imported']), (3, 2))
        self.assertEqual(row['flag'], 'Need 1 more')

    def test_more_imported_than_requested_flags_remove(self):
        self._request([{'term': str(self.fall.id)}])
        self._section(self.fall)
        self._section(self.fall_3l)
        self.assertEqual(self._row(reconcile(self.ay), 'Fall')['flag'],
                         'Remove 1')

    def test_not_teaching_with_rolled_over_section_flags_remove(self):
        self._request([], teaching='no')
        self._section(self.spring)
        row = self._row(reconcile(self.ay), 'Spring')
        self.assertEqual((row['requested'], row['flag']), (0, 'Remove 1'))

    def test_cancelled_sections_and_unanswered_schools_are_ignored(self):
        self._request([{'term': str(self.fall.id)}])
        self._section(self.fall)
        self._section(self.fall, status='C')
        self._section(self.fall, hs=self.other_hs)  # no request there
        rows = reconcile(self.ay)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['flag'], 'OK')

    def test_flagged_only_drops_matching_rows(self):
        self._request([{'term': str(self.fall.id)}])
        self._section(self.fall)
        self.assertEqual(reconcile(self.ay, flagged_only=True), [])

    def test_full_year_counts_in_configured_term(self):
        Setting.objects.filter(key='cis_future_sections').update(value={
            'academic_year': str(self.ay.id),
            'sis_full_year_term_code': '6L'})
        self._request([{'term': str(self.fall.id), 'full_year': True}])
        self._section(self.spring_6l)
        rows = reconcile(self.ay)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0]['term'], rows[0]['flag']), ('Spring', 'OK'))

    def test_full_year_without_setting_stays_in_its_term(self):
        self._request([{'term': str(self.fall.id), 'full_year': True}])
        self._section(self.spring_6l)
        rows = reconcile(self.ay)
        self.assertEqual(self._row(rows, 'Fall')['flag'], 'Need 1 more')
        self.assertEqual(self._row(rows, 'Spring')['flag'], 'Remove 1')

    def test_reconcile_writes_nothing(self):
        fc = self._request([{'term': str(self.fall.id)}])
        before = (fc.section_info, fc.meta, fc.status)
        self._section(self.fall)
        reconcile(self.ay)
        fc.refresh_from_db()
        self.assertEqual((fc.section_info, fc.meta, fc.status), before)
        self.assertEqual(fc.sis_sections.count(), 0)


class CandidateTests(_Base):
    def test_suggests_same_term_and_teacher_only(self):
        fc = self._request([{'term': str(self.fall.id)}])
        good = self._section(self.fall_3l)
        other_teacher = Teacher.objects.create(user=CustomUser.objects.create(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com'))
        wrong_teacher = self._section(self.fall, teacher=other_teacher)
        wrong_term = self._section(self.spring)
        qs, suggested = candidate_sections(fc)
        self.assertEqual(set(qs), {good, wrong_teacher, wrong_term})
        self.assertEqual(suggested, {good.id})

    def test_section_linked_to_another_request_is_not_offered(self):
        fc = self._request([{'term': str(self.fall.id)}])
        other_t = Teacher.objects.create(user=CustomUser.objects.create(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com'))
        other_cert = TeacherCourseCertificate.objects.create(
            teacher_highschool=TeacherHighSchool.objects.create(
                teacher=other_t, highschool=self.hs),
            course=self.course, status='Teaching')
        other = self._request([{'term': str(self.fall.id)}], cert=other_cert)
        sec = self._section(self.fall)
        other.sis_sections.add(sec)
        qs, _ = candidate_sections(fc)
        self.assertNotIn(sec, qs)
        # ...but still offered to the request it is linked to.
        self.assertIn(sec, candidate_sections(other)[0])

    def test_link_records_history(self):
        fc = self._request([{'term': str(self.fall.id)}])
        sec = self._section(self.fall)
        user = CustomUser.objects.create(username=f'{_sfx()}@x.com')
        self.assertTrue(link_sections(fc, [sec], user))
        self.assertFalse(link_sections(fc, [sec], user))
        fc.refresh_from_db()
        self.assertEqual(list(fc.sis_sections.all()), [sec])
        self.assertIn('Linked SIS sections',
                      fc.meta['history'][-1]['action'])


class CEViewTests(_Base):
    def setUp(self):
        super().setUp()
        Group.objects.get_or_create(name='ce')
        self.ce = CustomUser.objects.create_user(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', password='pw')
        self.ce.groups.add(Group.objects.get(name='ce'))
        _safe_force_login(self.client, self.ce)
        self.actions = reverse('future_sections_ce:future_sections_actions')

    def test_get_modal_ticks_suggestions(self):
        fc = self._request([{'term': str(self.fall.id)}])
        sec = self._section(self.fall)
        response = self.client.get(self.actions, {
            'action': 'sis-sections', 'future_course_id': str(fc.id)})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(f'value="{sec.id}"', body)
        self.assertIn('checked', body)
        self.assertEqual(fc.sis_sections.count(), 0)  # GET links nothing

    def test_post_links_and_rejects_foreign_section(self):
        fc = self._request([{'term': str(self.fall.id)}])
        sec = self._section(self.fall)
        foreign = self._section(self.fall, hs=self.other_hs)
        bad = self.client.post(self.actions, {
            'action': 'sis-sections', 'future_course_id': str(fc.id),
            'sis_sections': [str(foreign.id)]})
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(self.actions, {
            'action': 'sis-sections', 'future_course_id': str(fc.id),
            'sis_sections': [str(sec.id)]})
        self.assertEqual(ok.json()['action'], 'reload_table')
        self.assertEqual(list(fc.sis_sections.all()), [sec])

    def test_bad_future_course_id_404s(self):
        response = self.client.get(self.actions, {
            'action': 'sis-sections', 'future_course_id': 'nope'})
        self.assertEqual(response.status_code, 404)

    def test_reconciliation_page_and_csv(self):
        self._request([{'term': str(self.fall.id), 'number_of_sections': 2}])
        self._section(self.fall)
        url = reverse('future_sections_ce:sis_reconciliation')
        html = self.client.get(url, {'academic_year': str(self.ay.id),
                                     'flagged_only': '1'})
        self.assertContains(html, 'Need 1 more')
        response = self.client.get(url, {
            'academic_year': str(self.ay.id), 'format': 'csv'})
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0][-1], 'Flag')
        self.assertEqual(rows[1][2:], ['Fall', '2', '1', '0', 'Need 1 more'])

    def test_reconciliation_requires_ce(self):
        self.client.logout()
        response = self.client.get(
            reverse('future_sections_ce:sis_reconciliation'),
            {'academic_year': str(self.ay.id)})
        self.assertEqual(response.status_code, 302)

    def test_ce_list_api_carries_link_count(self):
        fc = self._request([{'term': str(self.fall.id)}])
        fc.sis_sections.add(self._section(self.fall))
        from ..views.ce_api import FutureClassSectionViewSet
        from django.test import RequestFactory
        view = FutureClassSectionViewSet()
        view.request = RequestFactory().get(
            '/', {'academic_year': str(self.ay.id)})
        got = view.get_queryset().get(pk=fc.pk)
        self.assertEqual(got.sis_link_count, 1)


class CEListFeedQueryCountTests(_Base):
    """The CE Course Information feed must not query sis_sections per row
    (review I1): the link count travels in section_display.sis_link_count."""

    def setUp(self):
        super().setUp()
        self.ce = CustomUser.objects.create_user(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', password='pw')
        self.ce.groups.add(Group.objects.get(name='ce'))
        _safe_force_login(self.client, self.ce)
        self.url = reverse('future_sections_ce:future_class_section-list')

    def _add_rows(self, n):
        for _ in range(n):
            t = Teacher.objects.create(user=CustomUser.objects.create(
                username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com'))
            cert = TeacherCourseCertificate.objects.create(
                teacher_highschool=TeacherHighSchool.objects.create(
                    teacher=t, highschool=self.hs),
                course=self.course, status='Teaching')
            fc = self._request([{'term': str(self.fall.id)}], cert=cert)
            fc.sis_sections.add(self._section(self.fall))

    def _sis_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url, {
                'format': 'json', 'academic_year': str(self.ay.id)})
        self.assertEqual(response.status_code, 200)
        return [q['sql'] for q in ctx.captured_queries
                if 'futurecourse_sis_sections' in q['sql']]

    def test_sis_sections_not_serialized(self):
        self._add_rows(1)
        response = self.client.get(self.url, {
            'format': 'json', 'academic_year': str(self.ay.id)})
        data = response.json()
        rows = data.get('results', data)
        self.assertNotIn('sis_sections', rows[0])
        self.assertEqual(rows[0]['section_display']['sis_link_count'], 1)

    def test_link_queries_do_not_grow_with_rows(self):
        self._add_rows(2)
        two = len(self._sis_queries())
        self._add_rows(3)
        five = len(self._sis_queries())
        self.assertEqual(two, five)


class CSVExportHardeningTests(_Base):
    """Reconciliation CSV: formula cells neutralised, filename sanitised
    (review M1, M2)."""

    def setUp(self):
        super().setUp()
        ce = CustomUser.objects.create_user(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', password='pw')
        ce.groups.add(Group.objects.get(name='ce'))
        _safe_force_login(self.client, ce)

    def test_formula_cells_are_prefixed(self):
        self.hs.name = '=HYPERLINK("http://x")'
        self.hs.save()
        self._request([{'term': str(self.fall.id)}])
        response = self.client.get(
            reverse('future_sections_ce:sis_reconciliation'),
            {'academic_year': str(self.ay.id), 'format': 'csv'})
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[1][0], '\'=HYPERLINK("http://x")')
        self.assertEqual(rows[1][3], '1')  # numbers untouched

    def test_filename_is_sanitised(self):
        self.ay.name = '2026"; evil=1'
        self.ay.save()
        response = self.client.get(
            reverse('future_sections_ce:sis_reconciliation'),
            {'academic_year': str(self.ay.id), 'format': 'csv'})
        header = response['Content-Disposition']
        self.assertNotIn('";', header)
        self.assertEqual(header.count('"'), 2, header)

    def test_csv_safe_helper(self):
        from ..utils import csv_safe
        for raw in ('=1', '+1', '-1', '@a', '\tx', '\rx'):
            self.assertEqual(csv_safe(raw), "'" + raw)
        self.assertEqual(csv_safe('plain'), 'plain')
        self.assertEqual(csv_safe(3), 3)


class CancelledLinkedSectionTests(_Base):
    """A linked section later cancelled in the SIS stays linked and shows as
    cancelled, so a Save does not drop it silently (review M6)."""

    def setUp(self):
        super().setUp()
        ce = CustomUser.objects.create_user(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', password='pw')
        ce.groups.add(Group.objects.get(name='ce'))
        _safe_force_login(self.client, ce)
        self.actions = reverse('future_sections_ce:future_sections_actions')

    def test_cancelled_linked_section_is_kept_and_marked(self):
        fc = self._request([{'term': str(self.fall.id)}])
        sec = self._section(self.fall)
        fc.sis_sections.add(sec)
        sec.status = 'C'
        sec.save()
        qs, suggested = candidate_sections(fc)
        self.assertIn(sec, qs)
        self.assertNotIn(sec.id, suggested)
        body = self.client.get(self.actions, {
            'action': 'sis-sections', 'future_course_id': str(fc.id)}
        ).content.decode()
        self.assertIn(f'value="{sec.id}"', body)
        self.assertIn('Cancelled in SIS', body)
        ok = self.client.post(self.actions, {
            'action': 'sis-sections', 'future_course_id': str(fc.id),
            'sis_sections': [str(sec.id)]})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(list(fc.sis_sections.all()), [sec])

    def test_cancelled_unlinked_section_is_still_not_offered(self):
        fc = self._request([{'term': str(self.fall.id)}])
        sec = self._section(self.fall, status='C')
        self.assertNotIn(sec, candidate_sections(fc)[0])

    def test_label_without_class_number_does_not_repeat(self):
        from ..forms import SisSectionChoiceField
        sec = self._section(self.fall)
        sec.class_number = None
        label = SisSectionChoiceField(queryset=None).label_from_instance(sec)
        self.assertEqual(label.count(sec.section_number), 1, label)
        sec.class_number = 4321
        label = SisSectionChoiceField(queryset=None).label_from_instance(sec)
        self.assertIn(f'4321 ({sec.section_number})', label)


class SisSectionsModalIsCEOnlyTests(_Base):
    """The sis-sections action is CE-only (review M9): anonymous and
    school-side users are redirected and nothing is linked."""

    def _hit(self):
        fc = self._request([{'term': str(self.fall.id)}])
        sec = self._section(self.fall)
        url = reverse('future_sections_ce:future_sections_actions')
        get = self.client.get(url, {
            'action': 'sis-sections', 'future_course_id': str(fc.id)})
        post = self.client.post(url, {
            'action': 'sis-sections', 'future_course_id': str(fc.id),
            'sis_sections': [str(sec.id)]})
        return fc, get, post

    def test_anonymous_is_redirected(self):
        fc, get, post = self._hit()
        self.assertEqual((get.status_code, post.status_code), (302, 302))
        self.assertEqual(fc.sis_sections.count(), 0)

    def test_instructor_is_redirected(self):
        user = self.teacher.user
        user.groups.add(Group.objects.get(name='instructor'))
        _safe_force_login(self.client, user)
        fc, get, post = self._hit()
        self.assertEqual((get.status_code, post.status_code), (302, 302))
        self.assertEqual(fc.sis_sections.count(), 0)
