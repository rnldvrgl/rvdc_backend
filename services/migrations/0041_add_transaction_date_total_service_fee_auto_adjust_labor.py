from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0040_add_receipt_book"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="transaction_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="The date this service occurred. When set, payments are backdated to this date for remittance purposes.",
            ),
        ),
        migrations.AddField(
            model_name="serviceappliance",
            name="total_service_fee",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Total quoted fee (labor + parts combined). When auto_adjust_labor is on, labor_fee is auto-computed as total_service_fee minus parts cost.",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="serviceappliance",
            name="auto_adjust_labor",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, labor_fee is automatically adjusted so that labor_fee + parts = total_service_fee.",
            ),
        ),
    ]
