from django.test import SimpleTestCase

from ..forms import EmailNewTeacherForm


class _Course:
    def __init__(self, sections):
        self.section_info = {'sections': sections}


CHANGED = {'teacher_changed': 'yes', 'new_teacher_email': 'j@x.com',
           'new_teacher_name': 'Jane Roe'}
UNCHANGED = {'teacher_changed': 'no'}


def _form(course, **overrides):
    data = {
        'section_index': 0,
        'recipient': 'j@x.com',
        'subject': 'Hello',
        'message': 'Body {{link}}',
        'mode': 'start_app',
        'confirm_recipient': True,
    }
    data.update(overrides)
    return EmailNewTeacherForm(data=data, future_course=course)


class EmailNewTeacherFormTests(SimpleTestCase):
    def test_valid_payload_passes(self):
        self.assertTrue(_form(_Course([CHANGED])).is_valid())

    def test_section_index_out_of_range_is_rejected(self):
        form = _form(_Course([CHANGED]), section_index=5)
        self.assertFalse(form.is_valid())
        self.assertIn('section_index', form.errors)

    def test_negative_section_index_is_rejected(self):
        form = _form(_Course([CHANGED]), section_index=-1)
        self.assertFalse(form.is_valid())
        self.assertIn('section_index', form.errors)

    def test_section_not_marked_changed_is_rejected(self):
        # Stops a crafted POST emailing an arbitrary address via any record.
        form = _form(_Course([UNCHANGED]))
        self.assertFalse(form.is_valid())
        self.assertIn('section_index', form.errors)

    def test_invalid_recipient_is_rejected(self):
        form = _form(_Course([CHANGED]), recipient='not-an-email')
        self.assertFalse(form.is_valid())
        self.assertIn('recipient', form.errors)

    def test_missing_confirmation_is_rejected(self):
        form = _form(_Course([CHANGED]), confirm_recipient=False)
        self.assertFalse(form.is_valid())
        self.assertIn('confirm_recipient', form.errors)

    def test_blank_subject_is_rejected(self):
        form = _form(_Course([CHANGED]), subject='')
        self.assertFalse(form.is_valid())
        self.assertIn('subject', form.errors)

    def test_blank_message_is_rejected(self):
        form = _form(_Course([CHANGED]), message='')
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_unknown_mode_is_rejected(self):
        form = _form(_Course([CHANGED]), mode='something_else')
        self.assertFalse(form.is_valid())
        self.assertIn('mode', form.errors)

    def test_invite_mode_is_accepted(self):
        self.assertTrue(_form(_Course([CHANGED]), mode='invite').is_valid())

    def test_recipient_need_not_match_the_captured_address(self):
        # Staff may correct a typo the school admin made.
        self.assertTrue(
            _form(_Course([CHANGED]), recipient='corrected@x.com').is_valid())

    def test_section_is_available_after_validation(self):
        form = _form(_Course([CHANGED]))
        self.assertTrue(form.is_valid())
        self.assertEqual(form.section['new_teacher_name'], 'Jane Roe')

    def test_section_is_none_when_confirmation_missing(self):
        form = _form(_Course([CHANGED]), confirm_recipient=False)
        self.assertFalse(form.is_valid())
        self.assertIsNone(form.section)

    def test_section_is_none_when_subject_blank(self):
        form = _form(_Course([CHANGED]), subject='')
        self.assertFalse(form.is_valid())
        self.assertIsNone(form.section)

    def test_section_is_none_when_recipient_invalid(self):
        form = _form(_Course([CHANGED]), recipient='not-an-email')
        self.assertFalse(form.is_valid())
        self.assertIsNone(form.section)

    def test_broken_subject_shortcode_is_rejected(self):
        # A stray '{%' must be caught here, before any invite-mode side
        # effect runs (account creation, verification email).
        form = _form(_Course([CHANGED]), subject='Hi {% if %}')
        self.assertFalse(form.is_valid())
        self.assertIn('subject', form.errors)

    def test_broken_message_shortcode_is_rejected(self):
        form = _form(_Course([CHANGED]), message='Body {% if %}')
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_valid_shortcodes_in_message_still_pass(self):
        form = _form(_Course([CHANGED]),
                     message='Hello {{new_teacher_name}} — {{link}}')
        self.assertTrue(form.is_valid())

    def test_section_is_none_when_subject_shortcode_broken(self):
        form = _form(_Course([CHANGED]), subject='Hi {% if %}')
        self.assertFalse(form.is_valid())
        self.assertIsNone(form.section)


class ModeHelperTextTests(SimpleTestCase):
    """The two modes differ in what they create, not just in wording, so each
    choice explains itself in the compose box."""

    def _labels(self):
        form = EmailNewTeacherForm(future_course=_Course([CHANGED]))
        return {value: str(label)
                for value, label in form.fields['mode'].choices}

    def test_start_app_explains_that_nothing_is_created(self):
        label = self._labels()['start_app']
        self.assertIn('Nothing is created now', label)
        self.assertIn('public application form', label)

    def test_invite_explains_the_account_and_the_direct_link(self):
        label = self._labels()['invite']
        self.assertIn('applicant account', label)
        self.assertIn('links straight to it', label)
        self.assertIn('without re-entering', label)
        self.assertIn('confident the address is correct', label)

    def test_invite_does_not_promise_a_second_email(self):
        # Invite mode carries the verification link in the staff message; a
        # separate verification email is no longer sent.
        self.assertNotIn('separate verification email',
                         self._labels()['invite'])

    def test_mode_field_has_a_label_and_help_text(self):
        field = EmailNewTeacherForm(
            future_course=_Course([CHANGED])).fields['mode']
        self.assertTrue(field.label)
        self.assertIn('send the message you have written', field.help_text)

    def test_choice_values_are_unchanged(self):
        # The view and its tests branch on these exact values.
        self.assertEqual(sorted(self._labels()), ['invite', 'start_app'])
