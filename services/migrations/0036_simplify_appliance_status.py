from django.db import migrations, models


def convert_statuses(apps, schema_editor):
    """Convert old statuses to simplified ones."""
    ServiceAppliance = apps.get_model("services", "ServiceAppliance")
    # Everything that's not completed or cancelled becomes pending
    ServiceAppliance.objects.filter(
        status__in=[
            "received", "diagnosed", "in_repair",
            "ready_for_pickup", "reserved",
        ]
    ).update(status="pending")
    # delivered -> completed, installed -> completed
    ServiceAppliance.objects.filter(
        status__in=["delivered", "installed"]
    ).update(status="completed")


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0035_add_items_review_fields"),
    ]

    operations = [
        # First convert data
        migrations.RunPython(convert_statuses, migrations.RunPython.noop),
        # Then alter the field
        migrations.AlterField(
            model_name="serviceappliance",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
