"""
Convert integer quantity fields to DecimalField (supports fractional units like kg, ft)
and add waste_tolerance_percentage to Item for marginal inventory tracking.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0041_add_deleted_at_soft_delete"),
    ]

    operations = [
        # ---------- Item: add waste_tolerance_percentage ----------
        migrations.AddField(
            model_name="item",
            name="waste_tolerance_percentage",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text=(
                    "Acceptable waste/loss % when dispensing "
                    "(e.g. 5.00 = 5% tolerance for freon, copper tubes)."
                ),
                max_digits=5,
            ),
        ),
        # ---------- Stock: quantity  integer → decimal ----------
        migrations.AlterField(
            model_name="stock",
            name="quantity",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Total quantity in stock (supports decimals for kg, ft, etc.).",
                max_digits=10,
            ),
        ),
        migrations.AlterField(
            model_name="stock",
            name="reserved_quantity",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Quantity reserved for active services.",
                max_digits=10,
            ),
        ),
        migrations.AlterField(
            model_name="stock",
            name="low_stock_threshold",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Threshold below which stock is considered low.",
                max_digits=10,
            ),
        ),
        # ---------- StockRoomStock: quantity integer → decimal ----------
        migrations.AlterField(
            model_name="stockroomstock",
            name="quantity",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Total quantity in stockroom (supports decimals for kg, ft, etc.).",
                max_digits=10,
            ),
        ),
        migrations.AlterField(
            model_name="stockroomstock",
            name="low_stock_threshold",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Threshold below which stock is considered low.",
                max_digits=10,
            ),
        ),
    ]
