"""No test module may hardcode the nested `future_sections.future_sections` path.

The suite ships inside the wheel and runs in two deployment shapes: the
in-tree editable submodule, where this package imports as
`future_sections.future_sections`, and a pip-only tenant, where it is flat.
A module that spells either prefix out fails to import in the other layout —
which is how 28 of 32 tests came to error on every pip-only tenant.

Use a relative import, or `PKG` from this package's `__init__` where a string
is required.
"""
import os

from django.test import SimpleTestCase

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
NESTED_PREFIX = 'future_sections' + '.future_sections'
# The resolver itself names both layouts; that is its job.
EXEMPT = {'__init__.py', os.path.basename(__file__)}


class NoHardcodedPackagePrefixTests(SimpleTestCase):

    def test_no_test_module_spells_out_the_nested_prefix(self):
        offenders = []
        for name in sorted(os.listdir(TESTS_DIR)):
            if not name.endswith('.py') or name in EXEMPT:
                continue
            with open(os.path.join(TESTS_DIR, name), encoding='utf-8') as fh:
                for lineno, line in enumerate(fh, 1):
                    if NESTED_PREFIX in line:
                        offenders.append(f'{name}:{lineno}: {line.strip()}')
        self.assertEqual(offenders, [], '\n'.join(offenders))
