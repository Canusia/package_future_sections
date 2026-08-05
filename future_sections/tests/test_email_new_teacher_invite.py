from unittest import mock

from django.contrib.auth.models import Group
from django.core import mail
from django.test import override_settings

from cis.models.customuser import CustomUser

from future_sections.future_sections.tests.test_email_new_teacher_send import (
    LOCMEM, _Base, _flush,
)
from future_sections.future_sections.utils import (
    ExistingAccountNotApplicantError, get_or_create_applicant,
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

    def test_no_separate_verification_email_is_sent(self):
        # The staff email now carries the verification link itself, so a
        # second mail would duplicate it and split the teacher's attention.
        TeacherApplicant = _applicant_model()
        with mock.patch.object(
                TeacherApplicant, 'send_verification_request_email') as send:
            self._post(mode='invite')
        self.assertFalse(send.called)

    def test_staff_email_carries_the_verification_link(self):
        # start_app would ask the invited teacher to register from scratch and
        # collide with the account just created for them.
        from django.urls import reverse
        TeacherApplicant = _applicant_model()
        self._post(mode='invite')
        _flush()
        applicant = TeacherApplicant.objects.get(
            user__email='jane@zillah.test')
        verify_path = reverse(
            'applicant_app:verify_email',
            kwargs={'verification_id': applicant.verification_id})
        body = mail.outbox[0].body + str(mail.outbox[0].alternatives)
        self.assertIn(verify_path, body)
        self.assertNotIn(reverse('applicant_app:start_app'), body)

    def test_start_app_mode_still_links_to_start_app(self):
        from django.urls import reverse
        self._post(mode='start_app')
        _flush()
        body = mail.outbox[0].body + str(mail.outbox[0].alternatives)
        self.assertIn(reverse('applicant_app:start_app'), body)
        self.assertNotIn('verify_email', body)

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

    def test_existing_applicant_only_user_is_reused(self):
        # A user whose only role is 'applicant' (e.g. a returning invitee)
        # is fine to reuse.
        applicant_group, _ = Group.objects.get_or_create(name='applicant')
        user = CustomUser.objects.create(
            username='jane@zillah.test', email='jane@zillah.test',
            first_name='Jane', last_name='Roe')
        user.groups.add(applicant_group)
        before = CustomUser.objects.count()
        TeacherApplicant = _applicant_model()
        with mock.patch.object(TeacherApplicant,
                               'send_verification_request_email'):
            response = self._post(mode='invite')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CustomUser.objects.count(), before)

    def test_privileged_existing_account_is_refused(self):
        # An address that already belongs to an instructor/student/ce
        # account must not be reused as an applicant.
        for role in ('instructor', 'student', 'ce'):
            with self.subTest(role=role):
                CustomUser.objects.filter(
                    email='jane@zillah.test').delete()
                group, _ = Group.objects.get_or_create(name=role)
                user = CustomUser.objects.create(
                    username='jane@zillah.test', email='jane@zillah.test',
                    first_name='Jane', last_name='Roe')
                user.groups.add(group)

                user_count_before = CustomUser.objects.count()
                TeacherApplicant = _applicant_model()
                applicant_count_before = TeacherApplicant.objects.count()

                with mock.patch.object(
                        TeacherApplicant,
                        'send_verification_request_email') as send:
                    response = self._post(mode='invite')

                _flush()
                self.assertEqual(response.status_code, 400)
                self.assertIn('not an applicant',
                               response.json()['message'])
                self.assertEqual(CustomUser.objects.count(),
                                  user_count_before)
                self.assertEqual(TeacherApplicant.objects.count(),
                                  applicant_count_before)
                self.assertFalse(send.called)
                self.assertEqual(len(mail.outbox), 0)


class GetOrCreateApplicantRoleGuardTests(_Base):
    """Unit-level coverage of the role guard directly on the helper."""

    def test_no_roles_is_reused(self):
        user = CustomUser.objects.create(
            username='noroles@zillah.test', email='noroles@zillah.test')
        before = CustomUser.objects.count()
        applicant, _created = get_or_create_applicant(
            'noroles@zillah.test', 'No Roles')
        self.assertEqual(applicant.user_id, user.id)
        self.assertEqual(CustomUser.objects.count(), before)

    def test_applicant_role_is_reused(self):
        group, _ = Group.objects.get_or_create(name='applicant')
        user = CustomUser.objects.create(
            username='onlyapplicant@zillah.test',
            email='onlyapplicant@zillah.test')
        user.groups.add(group)
        before = CustomUser.objects.count()
        applicant, _created = get_or_create_applicant(
            'onlyapplicant@zillah.test', 'Only Applicant')
        self.assertEqual(applicant.user_id, user.id)
        self.assertEqual(CustomUser.objects.count(), before)

    def test_instructor_role_is_refused(self):
        group, _ = Group.objects.get_or_create(name='instructor')
        user = CustomUser.objects.create(
            username='teacher@zillah.test', email='teacher@zillah.test')
        user.groups.add(group)
        with self.assertRaises(ExistingAccountNotApplicantError):
            get_or_create_applicant('teacher@zillah.test', 'A Teacher')
