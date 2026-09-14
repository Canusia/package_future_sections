"""Settings page consolidation and key/value option lists.

- The Reviewer Roles checkbox list duplicated the Reviewer Roles & Order
  card, so the card is now the only control: `reviewer_roles` is a hidden
  field derived from `reviewer_role_config` on save.
- The card's rows are drag-reorderable like the Teaching Form Fields table.
- Assign a mentor during review? sits directly after the card.
- `instruction_modes` / `location_options` accept `value:Label` pairs like
  `course_request_types`, and stored values render as their labels.
"""
import json

from django import forms as djforms
from django.http import QueryDict
from django.test import RequestFactory, SimpleTestCase, TestCase

from crispy_forms.utils import render_crispy_form

from cis.models.customuser import CustomUser
from cis.models.settings import Setting

from ..forms import TeacherCourseSectionForm, build_course_type_choices
from ..schemas import TeachingSectionFieldSchema
from ..settings.future_sections import future_sections
from ..utils import build_section_choice_labels

REPORT_ID = '0f4e3b1a-1111-2222-3333-444455556666'


def _request():
    user = CustomUser.objects.create(
        username='ce-card@x.com', email='ce-card@x.com', is_active=True)
    request = RequestFactory().get(f'/?report_id={REPORT_ID}')
    request.user = user
    return request


def _qdict(data):
    qd = QueryDict(mutable=True)
    for key, value in data.items():
        if isinstance(value, (list, tuple)):
            for v in value:
                qd.appendlist(key, v)
        else:
            qd[key] = value
    return qd


class ReviewerRolesCardIsTheOnlyControlTests(TestCase):

    def test_reviewer_roles_is_hidden(self):
        form = future_sections(_request())
        self.assertIsInstance(
            form.fields['reviewer_roles'].widget, djforms.MultipleHiddenInput)

    def test_no_reviewer_roles_checkbox_list_is_rendered(self):
        html = render_crispy_form(future_sections(_request()))
        self.assertNotRegex(
            html, r'<input[^>]*type="checkbox"[^>]*name="reviewer_roles"')
        self.assertIn('Reviewer Roles &amp; Order', html)

    def test_reviewer_roles_is_derived_from_the_card_config_in_weight_order(self):
        form = future_sections(_request(), data=_qdict({
            'require_review': '1',
            'reviewer_role_config': '{"Dean": 2, "Faculty": 1}',
        }))
        form.is_valid()
        self.assertNotIn('reviewer_roles', form.errors)
        self.assertEqual(form.cleaned_data['reviewer_roles'],
                         ['Faculty', 'Dean'])

    def test_an_empty_card_with_review_on_is_an_error(self):
        form = future_sections(_request(), data=_qdict({
            'require_review': '1',
            'reviewer_role_config': '{}',
        }))
        form.is_valid()
        self.assertIn('reviewer_roles', form.errors)


class ReviewerRolesCardIsReorderableTests(TestCase):

    def _html(self, config):
        Setting.objects.create(
            key='cis_future_sections',
            value={'reviewer_role_config': json.dumps(config)})
        form = future_sections(
            _request(), initial={'reviewer_role_config': json.dumps(config)})
        return render_crispy_form(form)

    def test_rows_are_draggable_in_a_field_weights_table(self):
        html = self._html({'Faculty': 1})
        start = html.index('id="reviewer-role-config-ui"')
        card = html[start:html.index('</table>', start)]
        self.assertIn('field-weights-table', card)
        self.assertIn('<tr draggable="true" data-field="Faculty">', card)
        self.assertIn('fa-grip-vertical', card)

    def test_rows_render_in_saved_weight_order_with_excluded_roles_last(self):
        html = self._html({'Dean': 10, 'Faculty': 20})
        start = html.index('id="reviewer-role-config-ui"')
        card = html[start:html.index('</table>', start)]
        self.assertLess(card.index('data-field="Dean"'),
                        card.index('data-field="Faculty"'))
        self.assertLess(card.index('data-field="Faculty"'),
                        card.index('data-field="Dept. Chair"'))


class AssignMentorPlacementTests(SimpleTestCase):

    def test_assign_mentor_directly_follows_the_reviewer_card(self):
        names = list(future_sections.base_fields)
        self.assertEqual(names.index('assign_mentor'),
                         names.index('reviewer_role_config') + 1)
        self.assertEqual(names.index('mentor_default_role'),
                         names.index('assign_mentor') + 1)


class InstructionModeAndLocationPairsTests(TestCase):

    def _make_setting(self):
        Setting.objects.create(
            key='cis_future_sections',
            value={
                'teaching_form_config': json.dumps({
                    'fields': ['term', 'instruction_mode', 'location'],
                    'required': ['term'],
                }),
                'instruction_modes': 'f2f:Traditional (face-to-face)|Online',
                'location_options': 'main:Main Campus|North High',
            },
        )

    def test_the_selects_split_value_from_label(self):
        self._make_setting()
        form = TeacherCourseSectionForm()
        self.assertIn(('f2f', 'Traditional (face-to-face)'),
                      form.fields['instruction_mode'].choices)
        self.assertIn(('Online', 'Online'),
                      form.fields['instruction_mode'].choices)
        self.assertIn(('main', 'Main Campus'),
                      form.fields['location'].choices)
        self.assertIn(('North High', 'North High'),
                      form.fields['location'].choices)

    def test_stored_codes_render_as_labels(self):
        labels = build_section_choice_labels({
            'instruction_modes': 'f2f:Traditional (face-to-face)',
            'location_options': 'main:Main Campus',
        })
        out = TeachingSectionFieldSchema.format_section_display(
            {'instruction_mode': 'f2f', 'location': 'main'},
            '{instruction_mode} | {location}', False, labels)
        self.assertEqual(out, 'Traditional (face-to-face) | Main Campus')

    def test_add_teacher_selects_are_still_only_the_course_type_pair(self):
        built = build_course_type_choices({
            'instruction_modes': 'f2f:Face to face',
            'location_options': 'main:Main Campus',
        })
        self.assertEqual(set(built), {'course_type', 'course_request_type'})
