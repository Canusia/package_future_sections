from django.http import QueryDict
from django.test import TestCase, RequestFactory

from ..settings.future_sections import future_sections as FSForm


def _qdict(pairs):
    """Build a QueryDict from an iterable of (key, value) pairs, supporting multi-values."""
    qd = QueryDict(mutable=True)
    for key, value in pairs:
        if isinstance(value, (list, tuple)):
            for v in value:
                qd.appendlist(key, v)
        else:
            qd[key] = value
    return qd


class ReviewFieldsValidationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get('/?report_id=1')

    def test_require_review_yes_without_roles_fails(self):
        data = _qdict([
            ('require_review', '1'),
            ('reviewer_roles', []),
            ('assign_mentor', '2'),
            ('mentor_default_role', 'Faculty'),
        ])
        form = FSForm(self.request, data=data)
        form.is_valid()  # populate cleaned_data / errors for these fields
        self.assertIn('reviewer_roles', form.errors)

    def test_require_review_yes_with_roles_passes_field_check(self):
        data = _qdict([
            ('require_review', '1'),
            ('reviewer_roles', ['Faculty']),
            ('assign_mentor', '2'),
            ('mentor_default_role', 'Faculty'),
        ])
        form = FSForm(self.request, data=data)
        form.is_valid()
        self.assertNotIn('reviewer_roles', form.errors)

    def test_assign_mentor_yes_without_default_role_fails(self):
        # assign_mentor is only checked when review is on.
        data = _qdict([
            ('require_review', '1'),
            ('reviewer_roles', ['Faculty']),
            ('assign_mentor', '1'),
            ('mentor_default_role', ''),
        ])
        form = FSForm(self.request, data=data)
        form.is_valid()
        self.assertIn('mentor_default_role', form.errors)

    def test_assign_mentor_ignored_when_review_off(self):
        # When require_review='No', assign_mentor/mentor_default_role are not
        # validated even if assign_mentor is 'Yes' with no mentor role.
        data = _qdict([
            ('require_review', '2'),
            ('reviewer_roles', []),
            ('assign_mentor', '1'),
            ('mentor_default_role', ''),
        ])
        form = FSForm(self.request, data=data)
        form.is_valid()
        self.assertNotIn('mentor_default_role', form.errors)
        self.assertNotIn('reviewer_roles', form.errors)
