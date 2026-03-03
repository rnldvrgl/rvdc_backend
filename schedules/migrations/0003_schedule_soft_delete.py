# Generated migration - Add is_deleted + deleted_at to Schedule

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schedules", "0002_enhance_schedule_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="schedule",
            name="is_deleted",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name="schedule",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
