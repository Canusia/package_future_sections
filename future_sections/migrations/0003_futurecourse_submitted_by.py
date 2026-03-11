from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('future_sections', '0002_add_status_field_to_futurecourse'),
    ]

    operations = [
        migrations.AddField(
            model_name='futurecourse',
            name='submitted_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='fs_futurecourse_submitted',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
