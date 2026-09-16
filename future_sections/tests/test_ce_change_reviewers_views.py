from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.urls import reverse

from ..review.helpers import open_review_round, record_decision
from .test_review_change_reviewers import ChangeReviewersBase


def _safe_force_login(client, user):
    from django_login_history.models import post_login
    user_logged_in.disconnect(post_login)
    try:
        client.force_login(user)
    finally:
        user_logged_in.connect(post_login)


class CEChangeReviewersViewTests(ChangeReviewersBase):

    def setUp(self):
        super().setUp()
        ce, _ = Group.objects.get_or_create(name='ce')
        self.staff.groups.add(ce)
        self.faculty = self._reviewer('f@x.com', 'Faculty')
        self.chair = self._reviewer('c@x.com', 'Dept. Chair')
        open_review_round(self.fc)

    def _post(self, name, **data):
        return self.client.post(reverse(f'future_sections_ce:{name}'), data)

    def test_ce_skips_a_reviewer_and_the_request_advances(self):
        _safe_force_login(self.client, self.staff)
        resp = self._post('remove_reviewer', future_course_id=self.fc.id,
                          reviewer_id=self.faculty.pk, mode='skip')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')
        self.assertEqual(self._row(self.faculty).decision, 'skipped')
        self.assertEqual(self._row(self.faculty).skipped_by, self.staff)

    def test_ce_deletes_a_reviewer(self):
        _safe_force_login(self.client, self.staff)
        resp = self._post('remove_reviewer', future_course_id=self.fc.id,
                          reviewer_id=self.faculty.pk, mode='delete')
        self.assertEqual(resp.json()['status'], 'success')
        self.assertFalse(self.fc.reviews.filter(reviewer=self.faculty).exists())

    def test_removing_the_last_reviewer_says_the_request_is_reviewed(self):
        record_decision(self.fc, self.faculty, decision='approved')
        _safe_force_login(self.client, self.staff)
        resp = self._post('remove_reviewer', future_course_id=self.fc.id,
                          reviewer_id=self.chair.pk, mode='skip')
        self.assertIn('marked reviewed', resp.json()['message'])

    def test_an_unknown_mode_is_refused(self):
        _safe_force_login(self.client, self.staff)
        resp = self._post('remove_reviewer', future_course_id=self.fc.id,
                          reviewer_id=self.faculty.pk, mode='nuke')
        self.assertEqual(resp.status_code, 400)

    def test_a_refusal_is_a_400_with_the_reason(self):
        record_decision(self.fc, self.faculty, decision='approved')
        _safe_force_login(self.client, self.staff)
        resp = self._post('remove_reviewer', future_course_id=self.fc.id,
                          reviewer_id=self.faculty.pk, mode='skip')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('no outstanding decision', resp.json()['message'])

    def test_a_malformed_future_course_id_is_a_400(self):
        _safe_force_login(self.client, self.staff)
        resp = self._post('remove_reviewer', future_course_id='nope',
                          reviewer_id=self.faculty.pk, mode='skip')
        self.assertEqual(resp.status_code, 400)

    def test_get_is_not_allowed_on_remove(self):
        _safe_force_login(self.client, self.staff)
        resp = self.client.get(reverse('future_sections_ce:remove_reviewer'))
        self.assertEqual(resp.status_code, 405)

    def test_a_non_ce_user_cannot_remove_a_reviewer(self):
        _safe_force_login(self.client, self.chair)
        resp = self._post('remove_reviewer', future_course_id=self.fc.id,
                          reviewer_id=self.faculty.pk, mode='skip')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._row(self.faculty).decision, '')

    def test_a_non_ce_user_cannot_add_a_reviewer(self):
        newcomer = self._reviewer('n@x.com', 'Faculty')
        _safe_force_login(self.client, self.chair)
        resp = self._post('add_reviewer', future_course_id=self.fc.id,
                          reviewer_id=newcomer.pk)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(self.fc.reviews.filter(reviewer=newcomer).exists())

    def test_addable_reviewers_lists_candidates_and_floor(self):
        newcomer = self._reviewer('n@x.com', 'Dean')
        _safe_force_login(self.client, self.staff)
        resp = self.client.get(reverse('future_sections_ce:addable_reviewers'),
                               {'future_course_id': self.fc.id})
        body = resp.json()
        self.assertEqual(body['min_weight'], 10)
        self.assertEqual(
            [(r['reviewer_id'], r['role'], r['weight']) for r in body['reviewers']],
            [(str(newcomer.pk), 'Dean', 30)])

    def test_ce_adds_a_reviewer_at_a_chosen_weight(self):
        newcomer = self._reviewer('n@x.com', 'Dean')
        _safe_force_login(self.client, self.staff)
        resp = self._post('add_reviewer', future_course_id=self.fc.id,
                          reviewer_id=newcomer.pk, weight='20')
        self.assertEqual(resp.json()['status'], 'success')
        self.assertEqual(self._row(newcomer).weight, 20)

    def test_a_non_integer_weight_is_a_400(self):
        newcomer = self._reviewer('n@x.com', 'Dean')
        _safe_force_login(self.client, self.staff)
        resp = self._post('add_reviewer', future_course_id=self.fc.id,
                          reviewer_id=newcomer.pk, weight='soon')
        self.assertEqual(resp.status_code, 400)

    def test_an_oversized_weight_is_a_400_and_adds_nobody(self):
        newcomer = self._reviewer('n@x.com', 'Dean')
        _safe_force_login(self.client, self.staff)
        resp = self._post('add_reviewer', future_course_id=self.fc.id,
                          reviewer_id=newcomer.pk, weight='99999999999')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['message'], 'Missing or invalid parameters.')
        self.assertFalse(self.fc.reviews.filter(reviewer=newcomer).exists())

    def test_a_negative_weight_is_a_400(self):
        newcomer = self._reviewer('n@x.com', 'Dean')
        _safe_force_login(self.client, self.staff)
        resp = self._post('add_reviewer', future_course_id=self.fc.id,
                          reviewer_id=newcomer.pk, weight='-5')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(self.fc.reviews.filter(reviewer=newcomer).exists())

    def test_a_blank_weight_uses_the_configured_weight(self):
        newcomer = self._reviewer('n@x.com', 'Dean')
        _safe_force_login(self.client, self.staff)
        resp = self._post('add_reviewer', future_course_id=self.fc.id,
                          reviewer_id=newcomer.pk, weight='')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._row(newcomer).weight, 30)

    def test_a_weight_below_the_open_stage_is_a_400_with_the_reason(self):
        record_decision(self.fc, self.faculty, decision='approved')
        newcomer = self._reviewer('n@x.com', 'Faculty')
        _safe_force_login(self.client, self.staff)
        resp = self._post('add_reviewer', future_course_id=self.fc.id,
                          reviewer_id=newcomer.pk, weight='10')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('already closed', resp.json()['message'])
        self.assertFalse(self.fc.reviews.filter(reviewer=newcomer).exists())

    def test_addable_reviewers_on_a_request_not_under_review_is_a_400(self):
        from ..review.helpers import reset_review
        reset_review(self.fc)
        _safe_force_login(self.client, self.staff)
        resp = self.client.get(reverse('future_sections_ce:addable_reviewers'),
                               {'future_course_id': self.fc.id})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('not under review', resp.json()['message'])

    def test_removing_on_a_paused_request_says_to_notify_reviewers(self):
        other = self._reviewer('g@x.com', 'Faculty')
        from ..review.helpers import add_reviewer
        add_reviewer(self.fc, other.pk, by=self.staff)
        record_decision(self.fc, self.faculty, decision='not_approved')
        _safe_force_login(self.client, self.staff)
        resp = self._post('remove_reviewer', future_course_id=self.fc.id,
                          reviewer_id=other.pk, mode='skip')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Notify reviewers', resp.json()['message'])
