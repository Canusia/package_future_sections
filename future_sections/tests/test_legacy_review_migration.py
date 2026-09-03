from django.apps import apps as global_apps
from django.test import TestCase

from cis.models.customuser import CustomUser
from cis.models.term import AcademicYear

import importlib

from ..models import FutureCourse, SectionRequestReview
from . import PKG

# Migration modules start with a digit, so they cannot be imported with
# `from ..migrations import 0006_…`. PKG (see this package's __init__)
# resolves to the correct dotted path for either deployment shape, so this
# avoids hardcoding the nested prefix that test_no_hardcoded_package_prefix.py
# forbids.
legacy = importlib.import_module(
    f'{PKG}.migrations.0006_migrate_legacy_faculty_review')


class LegacyReviewConversionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.reviewer = CustomUser.objects.create(
            username='fiona@x.com', email='fiona@x.com', first_name='Fiona')

    def _fc(self, faculty_review):
        return FutureCourse.objects.create(
            academic_year=self.ay, status='reviewed',
            section_info={'sections': [], 'faculty_review': faculty_review})

    def test_current_decision_becomes_a_row(self):
        fc = self._fc({
            'decision': 'approved', 'comment': 'fine', 'mentor': None,
            'reviewer_id': str(self.reviewer.id), 'reviewer_name': 'Fiona',
            'reviewed_on': '2026-09-03T19:26:04+00:00', 'history': []})
        legacy.convert_legacy_reviews(global_apps)
        row = SectionRequestReview.objects.get(future_course=fc)
        self.assertEqual(row.decision, 'approved')
        self.assertEqual(row.comment, 'fine')
        self.assertEqual(row.reviewer, self.reviewer)
        self.assertEqual(row.round, 1)

    def test_history_entries_become_earlier_rounds(self):
        fc = self._fc({
            'decision': 'approved', 'comment': 'second', 'mentor': None,
            'reviewer_id': str(self.reviewer.id), 'reviewer_name': 'Fiona',
            'reviewed_on': '2026-09-03T19:26:04+00:00',
            'history': [{
                'decision': 'not_approved', 'comment': 'first',
                'mentor': None, 'reviewer_id': str(self.reviewer.id),
                'reviewer_name': 'Fiona',
                'reviewed_on': '2026-09-01T10:00:00+00:00'}]})
        legacy.convert_legacy_reviews(global_apps)
        rounds = dict(SectionRequestReview.objects
                      .filter(future_course=fc)
                      .values_list('round', 'decision'))
        self.assertEqual(rounds, {1: 'not_approved', 2: 'approved'})

    def test_review_round_is_set_to_the_latest_round(self):
        fc = self._fc({
            'decision': 'approved', 'comment': '', 'mentor': None,
            'reviewer_id': str(self.reviewer.id), 'reviewer_name': 'Fiona',
            'reviewed_on': '2026-09-03T19:26:04+00:00', 'history': []})
        legacy.convert_legacy_reviews(global_apps)
        fc.refresh_from_db()
        self.assertEqual(fc.review_round, 1)

    def test_the_json_key_is_left_in_place(self):
        fc = self._fc({
            'decision': 'approved', 'comment': '', 'mentor': None,
            'reviewer_id': str(self.reviewer.id), 'reviewer_name': 'Fiona',
            'reviewed_on': '2026-09-03T19:26:04+00:00', 'history': []})
        legacy.convert_legacy_reviews(global_apps)
        fc.refresh_from_db()
        self.assertIn('faculty_review', fc.section_info)

    def test_running_twice_creates_no_duplicates(self):
        self._fc({
            'decision': 'approved', 'comment': '', 'mentor': None,
            'reviewer_id': str(self.reviewer.id), 'reviewer_name': 'Fiona',
            'reviewed_on': '2026-09-03T19:26:04+00:00', 'history': []})
        legacy.convert_legacy_reviews(global_apps)
        legacy.convert_legacy_reviews(global_apps)
        self.assertEqual(SectionRequestReview.objects.count(), 1)

    def test_an_unknown_reviewer_id_is_skipped(self):
        self._fc({
            'decision': 'approved', 'comment': '', 'mentor': None,
            'reviewer_id': '99999999', 'reviewer_name': 'Ghost',
            'reviewed_on': '2026-09-03T19:26:04+00:00', 'history': []})
        legacy.convert_legacy_reviews(global_apps)
        self.assertEqual(SectionRequestReview.objects.count(), 0)

    def test_a_record_with_no_review_is_untouched(self):
        FutureCourse.objects.create(
            academic_year=self.ay, section_info={'sections': []})
        legacy.convert_legacy_reviews(global_apps)
        self.assertEqual(SectionRequestReview.objects.count(), 0)

    def test_backwards_is_a_no_op_and_leaves_existing_rows_intact(self):
        self._fc({
            'decision': 'approved', 'comment': '', 'mentor': None,
            'reviewer_id': str(self.reviewer.id), 'reviewer_name': 'Fiona',
            'reviewed_on': '2026-09-03T19:26:04+00:00', 'history': []})
        legacy.convert_legacy_reviews(global_apps)
        self.assertEqual(SectionRequestReview.objects.count(), 1)
        legacy.backwards(global_apps, None)
        self.assertEqual(SectionRequestReview.objects.count(), 1)
