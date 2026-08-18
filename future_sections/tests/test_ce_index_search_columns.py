"""Guard the CE index DataTable column names against FieldError 500s.

rest_framework_datatables turns each searchable column's ``data-name`` into a
``<path>__icontains`` filter when the global search box is used, so every
searchable ``data-name`` must be a real, text-searchable ORM path — a bare
ForeignKey (``submitted_by``) or a serializer-only key
(``prev_year_sections``) blows up with FieldError.

Columns listed in the NON_SEARCHABLE sets below must stay ``'searchable':
false`` in the matching DataTable ``columns`` config in index.html.
"""

import os
import re

from django.test import SimpleTestCase

from cis.models import TeacherCourseCertificate

from ..models import FutureCourse, FutureProjection


TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'templates', 'future_sections', 'ce', 'index.html',
)

TABLES = [
    ('records_all', FutureCourse, {'started_on', 'section_display', 'id'}),
    ('records_future_projections', FutureProjection, {
        'started_on', 'confirmed_administrators', 'confirmed_class_sections',
        'confirmed_choice_class_sections',
        'confirmed_facilitator_class_sections', 'meta', 'id'}),
    ('records_pending', TeacherCourseCertificate, {'prev_year_sections'}),
]


def _column_names(table_id):
    with open(TEMPLATE) as fh:
        html = fh.read()
    # Commented-out <th> blocks are dead columns; drop them before parsing.
    html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    thead = re.search(
        r'id="%s".*?<thead>(.*?)</thead>' % table_id, html, re.S).group(1)
    return re.findall(r"""data-name=['"]([^'"]+)['"]""", thead)


class CeIndexSearchColumnTests(SimpleTestCase):
    def test_searchable_columns_support_icontains(self):
        for table_id, model, non_searchable in TABLES:
            names = _column_names(table_id)
            self.assertTrue(names, '%s: template parse produced no columns' % table_id)

            for name in names:
                for path in [n.strip() for n in name.split(',')]:
                    if path in non_searchable:
                        continue
                    with self.subTest(table=table_id, column=path):
                        # filter() resolves the lookup eagerly; no DB access needed.
                        model.objects.filter(
                            **{'%s__icontains' % path.replace('.', '__'): 'a'})
