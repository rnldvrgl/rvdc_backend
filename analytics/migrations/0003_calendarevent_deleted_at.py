# Generated migration - Add deleted_at to CalendarEvent for soft-delete support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0002_rename_calendar_ev_event_d_idx_calendar_ev_event_d_52e5bf_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarevent",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
