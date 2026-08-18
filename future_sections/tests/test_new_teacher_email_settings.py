from django.test import SimpleTestCase

from ..settings.future_sections import (
    future_sections as FSForm,
    DEFAULT_NEW_TEACHER_EMAIL_SUBJECT,
    DEFAULT_NEW_TEACHER_EMAIL_MESSAGE,
)


class NewTeacherEmailSettingTests(SimpleTestCase):
    def test_both_fields_are_declared(self):
        for name in ('new_teacher_email_subject', 'new_teacher_email_message'):
            self.assertIn(name, FSForm.base_fields, name)

    def test_both_fields_are_optional(self):
        # Blank falls back to the built-in default rather than blocking a save.
        for name in ('new_teacher_email_subject', 'new_teacher_email_message'):
            self.assertFalse(FSForm.base_fields[name].required, name)

    def test_defaults_are_non_empty(self):
        self.assertTrue(DEFAULT_NEW_TEACHER_EMAIL_SUBJECT.strip())
        self.assertTrue(DEFAULT_NEW_TEACHER_EMAIL_MESSAGE.strip())

    def test_default_message_uses_the_link_shortcode(self):
        # Without {{link}} the recipient has no way to reach the application.
        self.assertIn('{{link}}', DEFAULT_NEW_TEACHER_EMAIL_MESSAGE)

    def test_help_text_lists_the_shortcodes(self):
        help_text = FSForm.base_fields['new_teacher_email_message'].help_text
        for code in ('{{new_teacher_name}}', '{{course}}', '{{highschool}}',
                     '{{link}}'):
            self.assertIn(code, help_text, code)
