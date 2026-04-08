import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0048_remove_item_waste_tolerance_percentage"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Create DirectStockRequestBatch model
        migrations.CreateModel(
            name="DirectStockRequestBatch",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "requested_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="direct_stock_batches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        # 2. Add approved_quantity to StockRequest
        migrations.AddField(
            model_name="stockrequest",
            name="approved_quantity",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Quantity approved for release by admin (for direct requests).",
                max_digits=10,
                null=True,
            ),
        ),
        # 3. Add batch FK to StockRequest
        migrations.AddField(
            model_name="stockrequest",
            name="batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="items",
                to="inventory.directstockrequestbatch",
            ),
        ),
        # 4. Update SOURCE_CHOICES to include 'direct' option
        migrations.AlterField(
            model_name="stockrequest",
            name="source",
            field=models.CharField(
                choices=[
                    ("service_appliance", "Service Appliance Item"),
                    ("service", "Service Item"),
                    ("direct", "Direct Request"),
                ],
                help_text="Whether this request originated from an appliance item, service-level item, or direct clerk request.",
                max_length=20,
            ),
        ),
    ]
