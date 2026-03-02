from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("installations", "0014_airconunit_free_cleaning_service"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelPriceHistory",
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
                (
                    "retail_price",
                    models.DecimalField(decimal_places=2, max_digits=10),
                ),
                (
                    "discount_percentage",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=5,
                    ),
                ),
                (
                    "old_retail_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Previous retail price (null for initial)",
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "old_discount_percentage",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Previous discount percentage (null for initial)",
                        max_digits=5,
                        null=True,
                    ),
                ),
                (
                    "change_type",
                    models.CharField(
                        choices=[
                            ("initial", "Initial Price"),
                            ("price", "Price Change"),
                            ("discount", "Discount Change"),
                            ("price_and_discount", "Price & Discount Change"),
                        ],
                        default="price",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "aircon_model",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_history",
                        to="installations.airconmodel",
                    ),
                ),
            ],
            options={
                "verbose_name": "Price History",
                "verbose_name_plural": "Price Histories",
                "ordering": ["-changed_at"],
            },
        ),
    ]
