from django.db.utils import IntegrityError
from django.test import TestCase

from cis.models.customuser import CustomUser
from cis.models.term import AcademicYear

from ..models import FutureCourse, SectionRequestReview


class SectionRequestReviewModelTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ay = AcademicYear.objects.create(name='2099-2100')
        cls.fc = FutureCourse.objects.create(academic_year=cls.ay)
        cls.reviewer = CustomUser.objects.create(
            username='rev@x.com', email='rev@x.com')

    def test_a_snapshot_row_starts_undecided(self):
        row = SectionRequestReview.objects.create(
            future_course=self.fc, reviewer=self.reviewer,
            round=1, role='Faculty')
        self.assertEqual(row.decision, '')
        self.assertIsNone(row.decided_on)
        self.assertIsNone(row.mentor)

    def test_rows_are_reachable_from_the_request(self):
        SectionRequestReview.objects.create(
            future_course=self.fc, reviewer=self.reviewer,
            round=1, role='Faculty')
        self.assertEqual(self.fc.reviews.count(), 1)

    def test_one_row_per_reviewer_per_round(self):
        SectionRequestReview.objects.create(
            future_course=self.fc, reviewer=self.reviewer,
            round=1, role='Faculty')
        with self.assertRaises(IntegrityError):
            SectionRequestReview.objects.create(
                future_course=self.fc, reviewer=self.reviewer,
                round=1, role='Faculty')

    def test_the_same_reviewer_may_appear_in_a_later_round(self):
        SectionRequestReview.objects.create(
            future_course=self.fc, reviewer=self.reviewer,
            round=1, role='Faculty')
        SectionRequestReview.objects.create(
            future_course=self.fc, reviewer=self.reviewer,
            round=2, role='Faculty')
        self.assertEqual(self.fc.reviews.count(), 2)

    def test_decision_choices(self):
        self.assertEqual(
            SectionRequestReview.DECISION_CHOICES,
            [('approved', 'Approved'), ('not_approved', 'Not approved')])
