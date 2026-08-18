"""Option lists accept `value:Label` pairs and plain labels alike.

`instruction_modes` and `location_options` have always been plain
pipe-delimited labels, used as both value and label. The course-type fields
need distinct stored values so an option can be reworded without orphaning
saved records, so the parser accepts both forms and the old one keeps its
exact previous meaning.
"""
from django.test import TestCase

from ..forms import parse_choice_list


class ParseChoiceListTests(TestCase):

    def test_plain_labels_use_the_label_as_the_value(self):
        self.assertEqual(
            parse_choice_list('Online|Hybrid'),
            [('Online', 'Online'), ('Hybrid', 'Hybrid')],
        )

    def test_pairs_split_value_from_label(self):
        self.assertEqual(
            parse_choice_list(
                'dual:Dual Credit|cpl:Credit for Prior Learning', pairs=True),
            [('dual', 'Dual Credit'), ('cpl', 'Credit for Prior Learning')],
        )

    def test_only_the_first_colon_splits(self):
        # Labels legitimately contain colons; values do not.
        self.assertEqual(
            parse_choice_list('new:This is a: New Course', pairs=True),
            [('new', 'This is a: New Course')],
        )

    def test_mixed_forms_in_one_list(self):
        self.assertEqual(
            parse_choice_list('Online|dual:Dual Credit', pairs=True),
            [('Online', 'Online'), ('dual', 'Dual Credit')],
        )

    def test_whitespace_is_stripped_from_both_halves(self):
        self.assertEqual(
            parse_choice_list('  dual : Dual Credit  | Online ', pairs=True),
            [('dual', 'Dual Credit'), ('Online', 'Online')],
        )

    def test_blank_and_empty_inputs_give_an_empty_list(self):
        for raw in ('', '   ', None, '||', ' | '):
            self.assertEqual(parse_choice_list(raw), [], raw)
            self.assertEqual(parse_choice_list(raw, pairs=True), [], raw)

    def test_a_token_that_is_only_a_colon_is_dropped(self):
        self.assertEqual(
            parse_choice_list('Online|:|dual:Dual', pairs=True),
            [('Online', 'Online'), ('dual', 'Dual')])

    def test_a_pair_with_an_empty_label_falls_back_to_the_value(self):
        self.assertEqual(parse_choice_list('dual:', pairs=True), [('dual', 'dual')])

    def test_regression_bare_mode_does_not_split_a_label_containing_a_colon(self):
        # A plain instruction_modes/location_options label may legitimately
        # contain a colon (e.g. "Hybrid: F2F and Online"). Without pairs=True,
        # it must remain one whole choice with the colon intact, not split
        # into a separate value/label pair.
        self.assertEqual(
            parse_choice_list('Hybrid: F2F and Online'),
            [('Hybrid: F2F and Online', 'Hybrid: F2F and Online')],
        )
