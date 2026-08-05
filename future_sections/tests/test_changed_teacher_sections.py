from django.test import SimpleTestCase

from future_sections.future_sections.serializers import FutureCourseSerializer


class _Obj:
    """Stand-in for FutureCourse — the field only reads section_info."""
    def __init__(self, section_info):
        self.section_info = section_info


def _changed(section_info):
    return FutureCourseSerializer().get_changed_teacher_sections(
        _Obj(section_info))


class ChangedTeacherSectionsTests(SimpleTestCase):
    def test_only_sections_marked_changed_are_returned(self):
        out = _changed({'sections': [
            {'teacher_changed': 'no', 'term_name': 'Fall'},
            {'teacher_changed': 'yes', 'term_name': 'Spring',
             'new_teacher_name': 'Jane Roe', 'new_teacher_email': 'j@x.com'},
        ]})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['new_teacher_name'], 'Jane Roe')

    def test_index_is_the_position_in_sections(self):
        out = _changed({'sections': [
            {'teacher_changed': 'no'},
            {'teacher_changed': 'no'},
            {'teacher_changed': 'yes', 'new_teacher_email': 'j@x.com'},
        ]})
        self.assertEqual(out[0]['index'], 2)

    def test_missing_name_and_email_become_empty_strings(self):
        out = _changed({'sections': [{'teacher_changed': 'yes'}]})
        self.assertEqual(out[0]['new_teacher_name'], '')
        self.assertEqual(out[0]['new_teacher_email'], '')

    def test_no_changed_sections_yields_empty_list(self):
        self.assertEqual(
            _changed({'sections': [{'teacher_changed': 'no'}]}), [])

    def test_empty_and_missing_section_info_are_safe(self):
        self.assertEqual(_changed({}), [])
        self.assertEqual(_changed(None), [])

    def test_several_changed_sections_are_all_returned(self):
        out = _changed({'sections': [
            {'teacher_changed': 'yes', 'new_teacher_email': 'a@x.com'},
            {'teacher_changed': 'yes', 'new_teacher_email': 'b@x.com'},
        ]})
        self.assertEqual([e['index'] for e in out], [0, 1])

    def test_non_yes_values_do_not_count(self):
        for value in ('Yes', 'YES', 'true', '1', ''):
            self.assertEqual(
                _changed({'sections': [{'teacher_changed': value}]}), [],
                value)


class SectionDisplayCarriesChangedSectionsTests(SimpleTestCase):
    """`changed_teacher_sections` must also ride inside `section_display`.

    rest_framework_datatables filters each row down to the fields named in
    the `columns[i][data]` params the browser sends. A top-level serializer
    field with no matching `<th data-data=...>` is stripped before it reaches
    the CE table, so the email action silently never renders. `section_display`
    is a requested column, so nesting the list inside it survives the filter.
    """

    def test_section_display_includes_changed_teacher_sections(self):
        obj = _Obj({'teaching': 'yes', 'sections': [
            {'teacher_changed': 'yes', 'new_teacher_email': 'j@x.com',
             'new_teacher_name': 'Jane Roe'},
        ]})
        obj.section_display = []
        display = FutureCourseSerializer().get_section_display(obj)
        self.assertIn('changed_teacher_sections', display)
        self.assertEqual(display['changed_teacher_sections'][0]['index'], 0)

    def test_section_display_key_is_empty_when_nothing_flagged(self):
        obj = _Obj({'teaching': 'yes', 'sections': [{'teacher_changed': 'no'}]})
        obj.section_display = []
        display = FutureCourseSerializer().get_section_display(obj)
        self.assertEqual(display['changed_teacher_sections'], [])

    def test_section_display_keeps_its_existing_keys(self):
        obj = _Obj({'teaching': 'yes', 'sections': []})
        obj.section_display = []
        display = FutureCourseSerializer().get_section_display(obj)
        for key in ('teaching', 'displays', 'faculty_review'):
            self.assertIn(key, display, key)
