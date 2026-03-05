"""
Replace discount_percentage with manual promo_price on AirconModel and ModelPriceHistory.
"""

from decimal import Decimal
from django.db import migrations, models


def convert_discount_to_promo(apps, schema_editor):
    """Convert existing percentage discounts to manual promo prices."""
    AirconModel = apps.get_model("installations", "AirconModel")
    for model in AirconModel.objects.all():
        if model.discount_percentage and model.discount_percentage > 0:
            discount_fraction = model.discount_percentage / Decimal("100")
            model.promo_price = model.retail_price - (model.retail_price * discount_fraction)
            model.save(update_fields=["promo_price"])


def convert_history_discount_to_promo(apps, schema_editor):
    """Convert existing history discount_percentage to promo_price."""
    ModelPriceHistory = apps.get_model("installations", "ModelPriceHistory")
    for entry in ModelPriceHistory.objects.all():
        if entry.discount_percentage and entry.discount_percentage > 0:
            discount_fraction = entry.discount_percentage / Decimal("100")
            entry.promo_price = entry.retail_price - (entry.retail_price * discount_fraction)
        if entry.old_discount_percentage and entry.old_discount_percentage > 0 and entry.old_retail_price:
            discount_fraction = entry.old_discount_percentage / Decimal("100")
            entry.old_promo_price = entry.old_retail_price - (entry.old_retail_price * discount_fraction)
        # Update change_type values
        if entry.change_type == "discount":
            entry.change_type = "promo"
        elif entry.change_type == "price_and_discount":
            entry.change_type = "price_and_promo"
        entry.save()


class Migration(migrations.Migration):

    dependencies = [
        ("installations", "0016_airconmodel_cost_price"),
    ]

    operations = [
        # Step 1: Add new promo_price field to AirconModel
        migrations.AddField(
            model_name="airconmodel",
            name="promo_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Manual promotional price. If set and less than retail, this is the selling price.",
                max_digits=10,
                null=True,
            ),
        ),
        # Step 2: Add new fields to ModelPriceHistory
        migrations.AddField(
            model_name="modelpricehistory",
            name="promo_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Promo price at this point in history",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="modelpricehistory",
            name="old_promo_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Previous promo price (null for initial)",
                max_digits=10,
                null=True,
            ),
        ),
        # Step 3: Migrate data from discount_percentage to promo_price
        migrations.RunPython(
            convert_discount_to_promo,
            migrations.RunPython.noop,
        ),
        migrations.RunPython(
            convert_history_discount_to_promo,
            migrations.RunPython.noop,
        ),
        # Step 4: Update change_type choices on ModelPriceHistory
        migrations.AlterField(
            model_name="modelpricehistory",
            name="change_type",
            field=models.CharField(
                choices=[
                    ("initial", "Initial Price"),
                    ("price", "Price Change"),
                    ("promo", "Promo Price Change"),
                    ("price_and_promo", "Price & Promo Change"),
                ],
                default="price",
                max_length=20,
            ),
        ),
        # Step 5: Remove old discount fields
        migrations.RemoveField(
            model_name="airconmodel",
            name="discount_percentage",
        ),
        migrations.RemoveField(
            model_name="modelpricehistory",
            name="discount_percentage",
        ),
        migrations.RemoveField(
            model_name="modelpricehistory",
            name="old_discount_percentage",
        ),
    ]
