from django.test import SimpleTestCase

from future_sections.future_sections.schemas import TeachingSectionFieldSchema


class FileDisplayTests(SimpleTestCase):
    def test_file_value_renders_as_a_link_labelled_by_the_field(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'assessment_upload': 'https://files.test/a.pdf'},
            '{assessment_upload}')
        self.assertIn("href='https://files.test/a.pdf'", out)
        self.assertIn('Assessment Upload', out)
        self.assertIn('target=\'_blank\'', out)

    def test_empty_file_value_renders_as_nothing(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'assessment_upload': ''}, 'X {assessment_upload} Y')
        self.assertNotIn('href', out)
        self.assertEqual(out, 'X Y')


class DateDisplayTests(SimpleTestCase):
    def test_iso_date_renders_in_us_format(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'start_date': '2026-09-01'}, '{start_date}')
        self.assertEqual(out, '09/01/2026')

    def test_both_dates_render(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'start_date': '2026-09-01', 'end_date': '2027-05-30'},
            '{start_date} to {end_date}')
        self.assertEqual(out, '09/01/2026 to 05/30/2027')

    def test_unparseable_date_falls_back_to_the_raw_value(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'start_date': 'sometime'}, '{start_date}')
        self.assertEqual(out, 'sometime')

    def test_empty_date_renders_as_nothing(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'start_date': ''}, 'X {start_date} Y')
        self.assertEqual(out, 'X Y')


class ExistingBehaviourTests(SimpleTestCase):
    def test_syllabus_link_still_works(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'file': 'https://files.test/s.pdf'}, '{syllabus_link}')
        self.assertIn('Syllabus', out)
        self.assertIn('https://files.test/s.pdf', out)

    def test_boolean_and_plain_values_are_unchanged(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'full_year': True, 'estimated_enrollment': '25'},
            '{full_year} | {estimated_enrollment}')
        self.assertEqual(out, 'Yes | 25')

    def test_unused_placeholders_are_stripped(self):
        out = TeachingSectionFieldSchema.format_section_display(
            {'estimated_enrollment': '25'},
            '{estimated_enrollment} | {class_period}')
        self.assertEqual(out, '25')
