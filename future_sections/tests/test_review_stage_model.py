"""Storage for sequential review: a weight per reviewer row, a pause per
request."""
from django.test import TestCase
from django.utils import timezone

from cis.models.customuser import CustomUser

from ..models import FutureCourse, SectionRequestReview


def _user(email):
    return CustomUser.objects.create(username=email, email=email)


class ReviewWeightFieldTests(TestCase):

    def setUp(self):
        self.fc = FutureCourse.objects.create(review_round=1)

    def test_weight_defaults_to_zero_so_existing_rows_form_one_stage(self):
        row = SectionRequestReview.objects.create(
            future_course=self.fc, reviewer=_user('a@x.com'), round=1,
            role='Faculty')
        self.assertEqual(row.weight, 0)

    def test_weight_is_stored(self):
        row = SectionRequestReview.objects.create(
            future_course=self.fc, reviewer=_user('b@x.com'), round=1,
            role='Dean', weight=3)
        row.refresh_from_db()
        self.assertEqual(row.weight, 3)

    def test_default_ordering_is_round_then_weight(self):
        SectionRequestReview.objects.create(
            future_course=self.fc, reviewer=_user('late@x.com'), round=1,
            role='Dean', weight=2)
        SectionRequestReview.objects.create(
            future_course=self.fc, reviewer=_user('early@x.com'), round=1,
            role='Faculty', weight=1)
        weights = list(
            SectionRequestReview.objects.values_list('weight', flat=True))
        self.assertEqual(weights, [1, 2])


class ReviewPauseFieldTests(TestCase):

    def test_a_new_request_is_not_paused(self):
        fc = FutureCourse.objects.create()
        self.assertIsNone(fc.review_paused_on)
        self.assertFalse(fc.is_review_paused)

    def test_setting_the_timestamp_marks_it_paused(self):
        fc = FutureCourse.objects.create()
        fc.review_paused_on = timezone.now()
        fc.save(update_fields=['review_paused_on'])
        fc.refresh_from_db()
        self.assertTrue(fc.is_review_paused)

    def test_a_paused_request_is_still_locked_to_the_school(self):
        # Pause is deliberately not a status: pending_review keeps the
        # school locked out and leaves every badge/filter/export alone.
        fc = FutureCourse.objects.create(
            status='pending_review', review_paused_on=timezone.now())
        self.assertIn(fc.status, FutureCourse.LOCKED_STATUSES)
