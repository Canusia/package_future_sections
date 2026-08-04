from django.test import SimpleTestCase

from future_sections.future_sections.forms import EmailNewTeacherForm


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
