"""
Migration to simplify ServiceStatus choices.

Removes 'pending' and 'on_hold' statuses.
Migrates existing records to 'in_progress'.
"""

from django.db import migrations, models


def migrate_statuses_forward(apps, schema_editor):
    Service = apps.get_model("services", "Service")
    Service.objects.filter(status__in=["pending", "on_hold"]).update(status="in_progress")


def migrate_statuses_backward(apps, schema_editor):
    # No-op: we can't know which were originally pending vs in_progress
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0046_add_linked_service_flow_fields"),
    ]

    operations = [
        # First, migrate data
        migrations.RunPython(migrate_statuses_forward, migrate_statuses_backward),
        # Then, update field choices
        migrations.AlterField(
            model_name="service",
            name="status",
            field=models.CharField(
                choices=[
                    ("in_progress", "In Progress"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ],
                default="in_progress",
                max_length=30,
            ),
        ),
    ]
