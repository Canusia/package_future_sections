from django.http import QueryDict
from django.test import TestCase, RequestFactory

from ..settings.future_sections import (
    future_sections as FSForm,
)


def _qdict(pairs):
    """Build a QueryDict from an iterable of (key, value) pairs."""
    qd = QueryDict(mutable=True)
    for key, value in pairs:
        if isinstance(value, (list, tuple)):
            for v in value:
                qd.appendlist(key, v)
        else:
            qd[key] = value
    return qd


class PersonnelConfirmationTextRequirementTests(TestCase):
    """`confirm_new_personnel` is required only when personnel confirmation
    is actually being requested.

    The settings JS hides this field whenever
    `require_personnel_confirmation` is not 'Yes', so a field-level
    `required=True` made the whole settings form unsavable for any tenant
    that turned confirmation off — blocked by an error on a hidden field.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get('/?report_id=1')

    def _bind(self, require, text):
        data = _qdict([
            ('require_personnel_confirmation', require),
            ('confirm_new_personnel', text),
        ])
        form = FSForm(self.request, data=data)
        form.is_valid()  # populate cleaned_data / errors
        return form

    def test_field_is_not_unconditionally_required(self):
        self.assertFalse(FSForm.base_fields['confirm_new_personnel'].required)

    def test_confirmation_on_without_text_fails(self):
        form = self._bind('1', '')
        self.assertIn('confirm_new_personnel', form.errors)

    def test_confirmation_on_with_text_passes(self):
        form = self._bind('1', 'I confirm the personnel list is up to date.')
        self.assertNotIn('confirm_new_personnel', form.errors)

    def test_confirmation_off_without_text_passes(self):
        # The regression: 'No' + blank text must not block saving.
        form = self._bind('2', '')
        self.assertNotIn('confirm_new_personnel', form.errors)

    def test_confirmation_unselected_without_text_passes(self):
        form = self._bind('', '')
        self.assertNotIn('confirm_new_personnel', form.errors)

    def test_confirmation_off_with_text_passes(self):
        # Leftover text from a previous config is not an error.
        form = self._bind('2', 'Some stale text')
        self.assertNotIn('confirm_new_personnel', form.errors)
