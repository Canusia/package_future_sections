from unittest import mock

from django.core import mail
from django.test import override_settings

from cis.models.customuser import CustomUser

from future_sections.future_sections.tests.test_email_new_teacher_send import (
    LOCMEM, _Base, _flush,
)


def _applicant_model():
    import importlib.util
    if importlib.util.find_spec('instructor_app.instructor_app'):
        from instructor_app.instructor_app.models.teacher_applicant_model \
            import TeacherApplicant
    else:
        from instructor_app.models.teacher_applicant_model import (
            TeacherApplicant)
    return TeacherApplicant


@override_settings(EMAIL_BACKEND=LOCMEM, MAILER_EMAIL_BACKEND=LOCMEM)
class InviteModeTests(_Base):
    def test_creates_a_user_and_applicant(self):
        TeacherApplicant = _applicant_model()
        before = TeacherApplicant.objects.count()
        with mock.patch.object(TeacherApplicant,
                               'send_verification_request_email'):
            self._post(mode='invite')
        self.assertEqual(TeacherApplicant.objects.count(), before + 1)
        self.assertTrue(
            CustomUser.objects.filter(email='jane@zillah.test').exists())

    def test_sends_the_verification_email(self):
        TeacherApplicant = _applicant_model()
        with mock.patch.object(
                TeacherApplicant, 'send_verification_request_email') as send:
            self._post(mode='invite')
        self.assertTrue(send.called)

    def test_does_not_create_a_teacher_application(self):
        # complete_signup creates that record; a second one would be a
        # half-populated duplicate.
        import importlib.util
        if importlib.util.find_spec('instructor_app.instructor_app'):
            from instructor_app.instructor_app.models.teacher_applicant \
                import TeacherApplication
        else:
            from instructor_app.models.teacher_applicant import (
                TeacherApplication)
        before = TeacherApplication.objects.count()
        TeacherApplicant = _applicant_model()
        with mock.patch.object(TeacherApplicant,
                               'send_verification_request_email'):
            self._post(mode='invite')
        self.assertEqual(TeacherApplication.objects.count(), before)

    def test_existing_user_is_reused(self):
        CustomUser.objects.create(
            username='jane@zillah.test', email='jane@zillah.test',
            first_name='Jane', last_name='Roe')
        before = CustomUser.objects.count()
        TeacherApplicant = _applicant_model()
        with mock.patch.object(TeacherApplicant,
                               'send_verification_request_email'):
            self._post(mode='invite')
        self.assertEqual(CustomUser.objects.count(), before)

    def test_staff_email_is_still_sent(self):
        TeacherApplicant = _applicant_model()
        with mock.patch.object(TeacherApplicant,
                               'send_verification_request_email'):
            self._post(mode='invite')
        _flush()
        self.assertEqual(len(mail.outbox), 1)

    def test_applicant_failure_sends_no_staff_email(self):
        with mock.patch(
                'future_sections.future_sections.utils.get_or_create_applicant',
                side_effect=Exception('boom')):
            self._post(mode='invite')
        _flush()
        self.assertEqual(len(mail.outbox), 0)
