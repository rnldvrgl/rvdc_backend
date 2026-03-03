# Generated migration - Add is_deleted + deleted_at to Offense, and deleted_at to existing models

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0009_alter_leaverequest_is_half_day"),
    ]

    operations = [
        # Offense: add is_deleted + deleted_at
        migrations.AddField(
            model_name="offense",
            name="is_deleted",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name="offense",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # DailyAttendance: add deleted_at (already has is_deleted)
        migrations.AddField(
            model_name="dailyattendance",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # HalfDaySchedule: add deleted_at (already has is_deleted)
        migrations.AddField(
            model_name="halfdayschedule",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
