from django.test import SimpleTestCase, TestCase

from ..models import FutureCourse


class StatusChoiceTests(SimpleTestCase):
    def test_pending_review_is_a_status_choice(self):
        self.assertIn(
            ('pending_review', 'Pending Review'), FutureCourse.STATUS_CHOICES)

    def test_submitted_and_reviewed_are_unchanged(self):
        self.assertIn(('submitted', 'Submitted'), FutureCourse.STATUS_CHOICES)
        self.assertIn(('reviewed', 'Reviewed'), FutureCourse.STATUS_CHOICES)

    def test_locked_statuses_are_pending_review_and_reviewed(self):
        self.assertEqual(
            set(FutureCourse.LOCKED_STATUSES), {'pending_review', 'reviewed'})


class ReviewRoundFieldTests(TestCase):
    def test_review_round_defaults_to_zero(self):
        self.assertEqual(FutureCourse().review_round, 0)
