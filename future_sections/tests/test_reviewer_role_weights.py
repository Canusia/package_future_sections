"""Reviewer Roles & Order: the settings half of sequential review.

Ported from instructor_app's `reviewer_role_config` card — a JSON
{role: weight} dict, lower weight reviewed first. `reviewer_roles` remains
the list of participating roles (and the validation anchor); the card keeps
the two in sync.
"""
from django import forms as djforms
from django.http import QueryDict
from django.test import RequestFactory, TestCase

from crispy_forms.utils import render_crispy_form

from cis.models.course import CourseAdministrator
from cis.models.customuser import CustomUser
from cis.models.settings import Setting

from ..settings.future_sections import future_sections

REPORT_ID = '0f4e3b1a-1111-2222-3333-444455556666'


def _request():
    user = CustomUser.objects.create(
        username='ce-rrc@x.com', email='ce-rrc@x.com', is_active=True)
    request = RequestFactory().get(f'/?report_id={REPORT_ID}')
    request.user = user
    return request


def _settings_html():
    # form_action resolves reverse_lazy('setting:run_record', [report_id])
    # only when the layout is actually rendered, and that route is
    # UUID-only, so a plain `?report_id=1` request raises NoReverseMatch
    # here (though not in form.is_valid() calls elsewhere, which never
    # render). The card HTML also lives in form.helper.layout as a crispy
    # HTML(...) object, which str(form) never emits — render_crispy_form is
    # required to see it.
    return render_crispy_form(future_sections(_request()))


class ReviewerRoleConfigFieldTests(TestCase):

    def test_the_form_exposes_the_new_settings_keys(self):
        form = future_sections(_request())
        for name in ('reviewer_role_config', 'review_escalation_recipients',
                     'review_escalation_subject',
                     'review_escalation_message'):
            self.assertIn(name, form.fields, name)

    def test_the_card_renders_a_row_per_course_administrator_role(self):
        html = _settings_html()
        self.assertIn('Reviewer Roles &amp; Order', html)
        for role_value, _label in CourseAdministrator.ROLE_OPTIONS:
            self.assertIn(
                f'class="rrc-include" data-role="{role_value}"', html,
                role_value)
            # The weight input carries Bootstrap sizing classes alongside
            # rrc-weight (form-control form-control-sm rrc-weight), unlike
            # the plain checkbox, so match the substring rather than an
            # exact class attribute.
            self.assertIn(
                f'rrc-weight" data-role="{role_value}"', html, role_value)

    def test_the_config_field_is_hidden_because_the_card_drives_it(self):
        form = future_sections(_request())
        self.assertIsInstance(
            form.fields['reviewer_role_config'].widget, djforms.HiddenInput)


class ReviewerRoleConfigValidationTests(TestCase):

    def _data(self, **overrides):
        # Only the keys clean() inspects; the form is validated field by
        # field elsewhere (test_settings_review_fields.py). A plain dict
        # doesn't work here: clean_reviewer_roles/clean_lookback_terms call
        # self.data.getlist(), so this must be a QueryDict like the real
        # POST data (see test_settings_review_fields.py's _qdict).
        data = {
            'require_review': '1',
            'reviewer_roles': ['Faculty'],
            'reviewer_role_config': '{"Faculty": 1}',
        }
        data.update(overrides)
        qd = QueryDict(mutable=True)
        for key, value in data.items():
            if isinstance(value, (list, tuple)):
                for v in value:
                    qd.appendlist(key, v)
            else:
                qd[key] = value
        return qd

    def _errors(self, **overrides):
        form = future_sections(_request(), data=self._data(**overrides))
        form.is_valid()
        return form.errors

    def test_malformed_json_is_rejected(self):
        self.assertIn('reviewer_role_config',
                      self._errors(reviewer_role_config='not json'))

    def test_a_non_integer_weight_is_rejected(self):
        self.assertIn(
            'reviewer_role_config',
            self._errors(reviewer_role_config='{"Faculty": "first"}'))

    def test_a_role_outside_the_role_options_is_rejected(self):
        self.assertIn(
            'reviewer_role_config',
            self._errors(reviewer_role_config='{"Wizard": 1}'))

    def test_a_well_formed_config_passes(self):
        self.assertNotIn('reviewer_role_config', self._errors())

    def test_an_empty_config_passes_when_review_is_off(self):
        self.assertNotIn(
            'reviewer_role_config',
            self._errors(require_review='0', reviewer_roles=[],
                         reviewer_role_config='{}'))


class InstallDefaultsTests(TestCase):

    def test_install_seeds_a_single_stage_config(self):
        # One stage by default == today's parallel behaviour.
        future_sections(_request()).install()
        value = Setting.objects.get(key='cis_future_sections').value
        self.assertEqual(value['reviewer_role_config'],
                         '{"Faculty": 1, "Dept. Chair": 1, "Dean": 1}')
        self.assertEqual(value['review_escalation_recipients'], '')
        self.assertIn('{{reviewer_first_name}}',
                      value['review_escalation_message'])
