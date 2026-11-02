"""State-changing endpoints are POST-only and CSRF-checked (security re-review).

A GET must never delete, change a status, send mail or create a request:
with ``CSRF_COOKIE_SAMESITE='Lax'`` the session cookie rides along with a
top-level cross-site GET, so a crafted link clicked by a logged-in CE (or a
link prefetcher) would otherwise make the change. POSTs go through
CsrfViewMiddleware (DRF's SessionAuthentication for the portal API), so a
POST without the token is refused too.
"""
import uuid
from unittest import mock

from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from cis.models.customuser import CustomUser
from cis.models.highschool_administrator import (
    HSAdministrator, HSAdministratorPosition, HSPosition)

from ..models import FutureCourse, FutureSection
from . import PKG
from .test_email_new_teacher_send import _safe_force_login
from .test_term_year_views import _Base, _sfx


class _CE(_Base):
    def setUp(self):
        super().setUp()
        self.ce = CustomUser.objects.create_user(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', password='pw')
        self.ce.groups.add(Group.objects.get(name='ce'))
        _safe_force_login(self.client, self.ce)
        self.actions = reverse('future_sections_ce:future_sections_actions')
        self.bulk = reverse('future_sections_ce:bulk_actions')

    def _csrf_client(self):
        client = Client(enforce_csrf_checks=True)
        _safe_force_login(client, self.ce)
        return client

    def _fc(self, **kw):
        return FutureCourse.objects.create(
            teacher_course=self.cert, academic_year=self.other,
            section_info={'teaching': 'yes', 'sections': []}, **kw)


class DeleteSectionTests(_CE):
    def setUp(self):
        super().setUp()
        self.section = FutureSection.objects.create(
            future_course=self._fc(), section_info={})
        self.url = reverse('future_sections_ce:delete_future_section')

    def test_get_is_refused_and_deletes_nothing(self):
        response = self.client.get(self.url, {'section': str(self.section.id)})
        self.assertEqual(response.status_code, 405)
        self.assertTrue(FutureSection.objects.filter(pk=self.section.pk).exists())

    def test_post_without_csrf_token_is_refused(self):
        response = self._csrf_client().post(
            self.url, {'section': str(self.section.id)})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(FutureSection.objects.filter(pk=self.section.pk).exists())

    def test_post_deletes(self):
        response = self.client.post(self.url, {'section': str(self.section.id)})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FutureSection.objects.filter(pk=self.section.pk).exists())

    def test_post_with_a_malformed_id_is_a_404(self):
        response = self.client.post(self.url, {'section': 'not-a-uuid'})
        self.assertEqual(response.status_code, 404)


class BulkActionTests(_CE):
    ACTIONS = ('mark_as_reviewed', 'mark_as_submitted',
               'mark_as_pending_review', 'notify_next_stage')

    def test_get_is_refused_for_every_action(self):
        fc = self._fc(status='submitted')
        for action in self.ACTIONS:
            response = self.client.get(
                self.bulk, {'action': action, 'ids[]': [str(fc.id)]})
            self.assertEqual(response.status_code, 405, action)
        fc.refresh_from_db()
        self.assertEqual(fc.status, 'submitted')

    def test_post_without_csrf_token_is_refused(self):
        fc = self._fc(status='submitted')
        response = self._csrf_client().post(
            self.bulk, {'action': 'mark_as_reviewed', 'ids[]': [str(fc.id)]})
        self.assertEqual(response.status_code, 403)
        fc.refresh_from_db()
        self.assertEqual(fc.status, 'submitted')

    def test_post_changes_the_status(self):
        fc = self._fc(status='submitted')
        response = self.client.post(
            self.bulk, {'action': 'mark_as_reviewed', 'ids[]': [str(fc.id)]})
        self.assertEqual(response.json()['status'], 'success')
        fc.refresh_from_db()
        self.assertEqual(fc.status, 'reviewed')

    def test_missing_and_malformed_ids_are_counted_not_named(self):
        fc = self._fc(status='submitted')
        response = self.client.post(self.bulk, {
            'action': 'mark_as_reviewed',
            'ids[]': [str(fc.id), str(uuid.uuid4()), 'junk']})
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body['status'], 'warning')
        self.assertIn('Skipped 2 not found or not accessible', body['message'])
        self.assertNotIn('campus', body['message'])


class CEAjaxTests(_CE):
    def _get(self, action, year=None):
        return self.client.get(self.actions, {
            'action': action,
            'course_certificate': str(self.cert.certificate_id),
            'academic_year_id': str((year or self.other).id)})

    def _post(self, action, client=None):
        return (client or self.client).post(self.actions, {
            'action': action,
            'course_certificate': str(self.cert.certificate_id),
            'academic_year_id': str(self.other.id)})

    def _exists(self):
        return FutureCourse.objects.filter(
            teacher_course=self.cert, academic_year=self.other).exists()

    def test_get_not_teaching_writes_nothing(self):
        response = self._get('not-teaching-section')
        self.assertEqual(response.status_code, 405)
        self.assertFalse(self._exists())

    def test_post_not_teaching_marks_it(self):
        response = self._post('not-teaching-section')
        self.assertEqual(response.status_code, 200)
        fc = FutureCourse.objects.get(
            teacher_course=self.cert, academic_year=self.other)
        self.assertEqual(fc.section_info, {'teaching': 'no'})

    def test_post_not_teaching_without_csrf_token_is_refused(self):
        response = self._post('not-teaching-section', self._csrf_client())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self._exists())

    def test_get_remove_deletes_nothing(self):
        self._fc()
        response = self._get('remove-not-teaching-section')
        self.assertEqual(response.status_code, 405)
        self.assertTrue(self._exists())

    def test_post_remove_deletes(self):
        self._fc()
        response = self._post('remove-not-teaching-section')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._exists())

    def test_get_teaching_form_renders_without_creating_a_request(self):
        response = self._get('teaching-section')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Old Fall')
        self.assertFalse(self._exists())

    def test_get_teaching_form_of_an_existing_request_keeps_it(self):
        fc = self._fc()
        response = self._get('teaching-section')
        self.assertEqual(response.status_code, 200)
        fc.refresh_from_db()
        self.assertEqual(fc.section_info, {'teaching': 'yes', 'sections': []})

    def test_read_only_modals_still_open_on_get(self):
        fc = self._fc()
        for action in ('sis-sections', 'email-new-teacher'):
            response = self.client.get(self.actions, {
                'action': action, 'future_course_id': str(fc.id)})
            self.assertEqual(response.status_code, 200, action)


class SendPendingReminderTests(_CE):
    def setUp(self):
        super().setUp()
        self.url = reverse('future_sections_ce:send_pending_reminder')
        admin_user = CustomUser.objects.create_user(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', password='pw')
        self.pos = HSAdministratorPosition.objects.create(
            hsadmin=HSAdministrator.objects.create(user=admin_user),
            highschool=self.hs, position=HSPosition.objects.create(name='P'),
            status='Active')
        from cis.models.settings import Setting
        row = Setting.objects.get(key='cis_future_sections')
        row.value.update({'pending_notification_message': 'Hi',
                          'mode': 'active'})
        row.save()

    def _params(self):
        return {'highschool_id': str(self.hs.id),
                'academic_year_id': str(self.other.id),
                'admin_ids[]': [str(self.pos.id)]}

    @mock.patch(f'{PKG}.views.ce.send_html_mail')
    def test_get_is_refused_and_sends_nothing(self, send):
        response = self.client.get(self.url, self._params())
        self.assertEqual(response.status_code, 405)
        send.assert_not_called()

    @mock.patch(f'{PKG}.views.ce.send_html_mail')
    def test_post_without_csrf_token_is_refused(self, send):
        response = self._csrf_client().post(self.url, self._params())
        self.assertEqual(response.status_code, 403)
        send.assert_not_called()

    @mock.patch(f'{PKG}.views.ce.send_html_mail')
    def test_post_sends(self, send):
        response = self.client.post(self.url, self._params())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(send.call_count, 1)


class PortalApiTests(_Base):
    """The HS admin / instructor ``actions`` API of this package."""

    def setUp(self):
        super().setUp()
        self.user = CustomUser.objects.create_user(
            username=f'{_sfx()}@x.com', email=f'{_sfx()}@x.com', password='pw')
        self.user.groups.add(Group.objects.get(name='highschool_admin'))
        HSAdministratorPosition.objects.create(
            hsadmin=HSAdministrator.objects.create(user=self.user),
            highschool=self.hs, position=HSPosition.objects.create(name='C'),
            status='Active')
        _safe_force_login(self.client, self.user)

    def _params(self):
        return {'course_certificate_id': str(self.cert.certificate_id),
                'academic_year_id': str(self.other.id)}

    def _exists(self):
        return FutureCourse.objects.filter(
            teacher_course=self.cert, academic_year=self.other).exists()

    def test_get_mark_not_teaching_is_refused(self):
        url = reverse('future_sections_highschool_admin:actions-mark-not-teaching')
        response = self.client.get(url, self._params())
        self.assertEqual(response.status_code, 405)
        self.assertFalse(self._exists())

    def test_post_mark_not_teaching_marks_it(self):
        url = reverse('future_sections_highschool_admin:actions-mark-not-teaching')
        response = self.client.post(url, self._params())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self._exists())

    def test_post_mark_not_teaching_without_csrf_token_is_refused(self):
        client = Client(enforce_csrf_checks=True)
        _safe_force_login(client, self.user)
        url = reverse('future_sections_highschool_admin:actions-mark-not-teaching')
        response = client.post(url, self._params())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self._exists())

    def test_get_teaching_form_does_not_create_a_request(self):
        url = reverse('future_sections_highschool_admin:actions-mark-teaching')
        response = self.client.get(url, self._params())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Old Fall')
        self.assertFalse(self._exists())


class JavaScriptCallersPostTests(_CE):
    """The package's own callers send these as POST with the CSRF token."""

    def _read(self, *parts):
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, *parts), encoding='utf-8') as fh:
            return fh.read()

    def test_ce_index_posts_bulk_reminder_and_course_actions(self):
        src = self._read('templates', 'future_sections', 'ce', 'index.html')
        for marker in ('// bulk_actions: POST', '// send_pending_reminder: POST',
                       '// notify_next_stage: POST', '// course-action: POST'):
            self.assertIn(marker, src)

    def test_ce_index_defines_the_csrf_token_itself(self):
        """Tenants on an in-repo cis whose logged-base.html predates
        window.CSRF_TOKEN would 403 every POST; the page sets it if absent."""
        src = self._read('templates', 'future_sections', 'ce', 'index.html')
        self.assertIn('window.CSRF_TOKEN = window.CSRF_TOKEN || "{{ csrf_token }}"', src)

    def test_portal_js_posts_mark_not_teaching(self):
        src = self._read('staticfiles', 'future_sections', 'js',
                         'future_sections.js')
        self.assertIn("action === 'not-teaching-section'", src)
