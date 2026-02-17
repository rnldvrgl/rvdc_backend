# Generated migration for adding unit_price to ServiceAppliance
# and updating ApplianceStatus choices with reserved/installed

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0023_serviceappliance_labor_warranty_end_date_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceappliance",
            name="unit_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Custom unit price (used for second-hand units or overrides)",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="serviceappliance",
            name="status",
            field=models.CharField(
                choices=[
                    ("received", "Received"),
                    ("diagnosed", "Diagnosed"),
                    ("in_repair", "In Repair"),
                    ("completed", "Completed"),
                    ("ready_for_pickup", "Ready for Pickup"),
                    ("delivered", "Delivered"),
                    ("reserved", "Reserved"),
                    ("installed", "Installed"),
                ],
                default="received",
                max_length=20,
            ),
        ),
    ]
