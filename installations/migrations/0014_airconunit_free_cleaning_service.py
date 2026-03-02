# Generated migration for adding free_cleaning_service FK to AirconUnit

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("installations", "0013_airconmodel_warranty_fields"),
        ("services", "0023_serviceappliance_labor_warranty_end_date_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="airconunit",
            name="free_cleaning_service",
            field=models.ForeignKey(
                blank=True,
                help_text="The cleaning service created when free cleaning was redeemed",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="free_cleaning_units",
                to="services.service",
            ),
        ),
    ]
