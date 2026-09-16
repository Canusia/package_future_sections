"""Everything that reads a review decision treats `skipped` as "taken out
of the round", never as a verdict."""
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.test import RequestFactory
from django.urls import reverse

from ..reports.future_classes import _faculty_review_cells
from ..review.api import SectionRequestSerializer
from ..review.helpers import reviewed_for, open_review_round, skip_reviewer
from ..serializers import FutureCourseSerializer
from .test_review_change_reviewers import ChangeReviewersBase


def _safe_force_login(client, user):
    from django_login_history.models import post_login
    user_logged_in.disconnect(post_login)
    try:
        client.force_login(user)
    finally:
        user_logged_in.connect(post_login)


class SkippedConsumersTests(ChangeReviewersBase):

    def setUp(self):
        super().setUp()
        self.faculty = self._reviewer('f@x.com', 'Faculty')
        self.other = self._reviewer('g@x.com', 'Faculty')
        open_review_round(self.fc)
        skip_reviewer(self.fc, self.faculty.pk, by=self.staff)
        self.fc.refresh_from_db()

    def test_skipped_request_is_not_in_the_reviewers_reviewed_tab(self):
        self.assertFalse(reviewed_for(self.faculty).exists())

    def test_reviewer_status_column_reads_skipped(self):
        request = RequestFactory().get('/')
        request.user = self.faculty
        data = SectionRequestSerializer(
            self.fc, context={'request': request}).data
        self.assertEqual(data['faculty_review_status'], 'Skipped')

    def test_detail_page_tells_a_skipped_reviewer_and_hides_the_form(self):
        group, _ = Group.objects.get_or_create(name='faculty')
        self.faculty.groups.add(group)
        _safe_force_login(self.client, self.faculty)
        resp = self.client.get(reverse(
            'future_sections_faculty:section_request_detail',
            args=[self.fc.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'You were removed from this review')
        self.assertNotContains(resp, 'Submit Review')

    def test_ce_payload_reports_skip_and_who_did_it(self):
        review = FutureCourseSerializer(self.fc).data['section_display']['review']
        self.assertEqual(review['skipped'], 1)
        # One skipped, one outstanding: a skip is not a decision.
        self.assertEqual(review['decided'], 0)
        self.assertEqual(review['total'], 2)
        self.assertEqual((review['approved'], review['not_approved']), (0, 0))
        self.assertTrue(review['can_change_reviewers'])
        by_id = {r['reviewer_id']: r for r in review['reviewers']}
        skipped = by_id[str(self.faculty.pk)]
        self.assertEqual(skipped['decision_code'], 'skipped')
        self.assertEqual(skipped['skipped_by'], 'F c')
        self.assertEqual(by_id[str(self.other.pk)]['skipped_by'], '')

    def test_export_labels_the_skip_and_keeps_the_stage_open(self):
        cells = _faculty_review_cells(self.fc)
        self.assertIn('Skipped', cells[4])
        self.assertEqual(cells[1], '10')
