from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cis', '__first__'),
        ('future_sections', '0008_sectionrequestreview_skipped'),
    ]

    operations = [
        migrations.AddField(
            model_name='futurecourse',
            name='sis_sections',
            field=models.ManyToManyField(
                blank=True,
                help_text='Imported SIS sections confirmed by staff as '
                          'fulfilling this request.',
                related_name='fs_future_courses',
                to='cis.classsection'),
        ),
    ]
