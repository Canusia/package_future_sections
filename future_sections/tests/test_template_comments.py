"""No shipped template may open a `{# #}` comment it does not close on the
same line.

Django's `{# ... #}` is a SINGLE-LINE construct. A `{#` whose `#}` sits on a
later line is not a comment at all — the template engine emits the whole run
of text verbatim, so the "comment" renders into the page for every user to
read:

    >>> Template('A{# one\\n two #}B').render(Context({}))
    'A{# one\\n two #}B'

Multi-line commentary must use `{% comment %} ... {% endcomment %}`, which
renders nothing. This shipped in teaching_course.html once already, leaking
three lines of implementation notes into the teaching form, so the rule gets
a test rather than a docstring.

The scan is deliberately static (like test_no_hardcoded_package_prefix.py):
it needs no client, fixtures or URL config, so it covers every template the
wheel ships including ones no test renders.
"""
import os

from django.test import SimpleTestCase

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')


def _unterminated_comment_lines(path):
    """Return `(lineno, text)` for each line opening a `{#` it never closes.

    Counting occurrences rather than testing for substring presence keeps a
    line that holds both a complete comment and a second, unterminated one
    from passing.
    """
    offenders = []
    with open(path, encoding='utf-8') as handle:
        for lineno, line in enumerate(handle, 1):
            if line.count('{#') > line.count('#}'):
                offenders.append((lineno, line.strip()))
    return offenders


class TemplateCommentTests(SimpleTestCase):

    def test_templates_dir_is_where_we_think_it_is(self):
        # A wrong path would make the real test below vacuously green.
        self.assertTrue(os.path.isdir(TEMPLATES_DIR), TEMPLATES_DIR)
        self.assertTrue(
            any(name.endswith('.html')
                for _root, _dirs, files in os.walk(TEMPLATES_DIR)
                for name in files),
            'found no .html templates to scan')

    def test_no_template_opens_a_comment_it_does_not_close(self):
        offenders = []
        for root, _dirs, files in os.walk(TEMPLATES_DIR):
            for name in sorted(files):
                if not name.endswith('.html'):
                    continue
                path = os.path.join(root, name)
                for lineno, text in _unterminated_comment_lines(path):
                    rel = os.path.relpath(path, TEMPLATES_DIR)
                    offenders.append(f'{rel}:{lineno}: {text}')
        self.assertEqual(
            offenders, [],
            'Django {# #} comments are single-line; use {% comment %} for '
            'multi-line commentary:\n' + '\n'.join(offenders))

    def test_the_detector_catches_a_multi_line_comment(self):
        # Guards the guard: proves the scan above can actually fail.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'bad.html')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('<p>ok</p>\n{# opened here\n   closed here #}\n')
            self.assertEqual(
                _unterminated_comment_lines(path),
                [(2, '{# opened here')])

    def test_the_detector_accepts_a_single_line_comment(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'good.html')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('{# all on one line #}\n{% comment %}\nx\n'
                             '{% endcomment %}\n')
            self.assertEqual(_unterminated_comment_lines(path), [])
