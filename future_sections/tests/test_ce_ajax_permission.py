"""The CE ajax dispatcher must be CE-only.

index/detail/settings are each wrapped in user_passes_test(user_has_cis_role);
the ajax path was not, so any authenticated user could drive CE actions.
"""

from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.test import TestCase
from django.urls import reverse

from cis.models.customuser import CustomUser


def _safe_force_login(client, user):
    # django_login_history's post_login signal handler blows up under the
    # test client (no real REMOTE_ADDR), unrelated to the permission gate
    # under test here. Same workaround used in test_review_views.py.
    from django_login_history.models import post_login
    user_logged_in.disconnect(post_login)
    try:
        client.force_login(user)
    finally:
        user_logged_in.connect(post_login)


class CEAjaxPermissionTests(TestCase):
    def setUp(self):
        for name in ('ce', 'instructor', 'student', 'highschool_admin'):
            Group.objects.get_or_create(name=name)
        self.url = reverse('future_sections_ce:future_sections_actions')

    def _user(self, email, group):
        user = CustomUser.objects.create_user(
            username=email, email=email, password='pw')
        user.groups.add(Group.objects.get(name=group))
        return user

    def test_anonymous_is_redirected(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 403))

    def test_non_ce_user_is_rejected(self):
        user = self._user('s@x.com', 'student')
        _safe_force_login(self.client, user)
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 403))
        self.assertNotEqual(response.status_code, 200)

    def test_ce_user_is_allowed_through(self):
        user = self._user('ce@x.com', 'ce')
        _safe_force_login(self.client, user)
        # No action (or an unrecognized action) makes the view return None,
        # which the Django test client raises as a hard error rather than a
        # 500 response -- not a permission failure, but not assertable via
        # status code either. 'remove-not-teaching-section' with no matching
        # records is a real branch that always returns a 200 JsonResponse, so
        # it exercises the guard without depending on view-internal dispatch.
        response = self.client.get(
            self.url, {'action': 'remove-not-teaching-section'})
        self.assertNotIn(response.status_code, (302, 403))
