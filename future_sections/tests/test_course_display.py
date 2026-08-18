from types import SimpleNamespace

from django.test import SimpleTestCase

from ..utils import render_course_display


def _course(campus=None, name='Intro Bio', title='BIO 101', credit_hours=5):
    """Duck-typed stand-in for a cis Course (helper only reads attributes)."""
    return SimpleNamespace(
        name=name, title=title, credit_hours=credit_hours, campus=campus,
    )


class RenderCourseDisplayTests(SimpleTestCase):
    def test_default_template_uses_title(self):
        self.assertEqual(render_course_display('{course_title}', _course()), 'BIO 101')

    def test_existing_placeholders(self):
        out = render_course_display(
            '{course_name} / {course_title} / {credit_hours}', _course())
        self.assertEqual(out, 'Intro Bio / BIO 101 / 5')

    def test_campus_placeholders(self):
        campus = SimpleNamespace(name='Cheney', code='CHY')
        out = render_course_display(
            '{course_title} @ {campus_name} ({campus_code})', _course(campus=campus))
        self.assertEqual(out, 'BIO 101 @ Cheney (CHY)')

    def test_campus_placeholders_are_blank_when_campus_is_null(self):
        out = render_course_display(
            '{course_title} @ {campus_name}|{campus_code}', _course(campus=None))
        self.assertEqual(out, 'BIO 101 @ |')

    def test_unknown_placeholder_falls_back_to_title(self):
        self.assertEqual(render_course_display('{not_a_placeholder}', _course()), 'BIO 101')

    def test_blank_course_name_renders_empty(self):
        out = render_course_display('{course_name}{course_title}', _course(name=''))
        self.assertEqual(out, 'BIO 101')
