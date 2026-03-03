# Generated migration - Add is_deleted + deleted_at to Service, Schedule, Offense

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0026_add_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="is_deleted",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name="service",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
