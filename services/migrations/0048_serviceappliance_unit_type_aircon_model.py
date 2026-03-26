"""
Add unit_type and aircon_model fields to ServiceAppliance for pre-order support.

- unit_type: tracks whether the appliance is brand_new, second_hand, or pre_order
- aircon_model: FK to AirconModel for pre_order units (to convert to brand_new later)
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("installations", "0001_initial"),
        ("services", "0047_simplify_service_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceappliance",
            name="unit_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("brand_new", "Brand New"),
                    ("second_hand", "Second Hand"),
                    ("pre_order", "Pre-Order"),
                ],
                default="",
                help_text="Type of unit: brand_new (from inventory), second_hand (manual entry), or pre_order (not yet in stock).",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="serviceappliance",
            name="aircon_model",
            field=models.ForeignKey(
                blank=True,
                help_text="Reference to the aircon model for pre-order units. Used to assign the actual unit when it arrives.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pre_order_appliances",
                to="installations.airconmodel",
            ),
        ),
    ]
