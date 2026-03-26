from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0043_add_service_document_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceReceipt",
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
                    "service",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="receipts",
                        to="services.service",
                    ),
                ),
                (
                    "receipt_number",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        null=True,
                        help_text="Official Receipt or Sales Invoice number.",
                    ),
                ),
                (
                    "receipt_book",
                    models.CharField(
                        blank=True,
                        max_length=50,
                        null=True,
                        help_text="Receipt book number.",
                    ),
                ),
                (
                    "document_type",
                    models.CharField(
                        choices=[("or", "Official Receipt"), ("si", "Sales Invoice")],
                        default="or",
                        max_length=2,
                        help_text="OR (main stall) or SI (sub stall).",
                    ),
                ),
                (
                    "with_2307",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this receipt has an attached BIR Form 2307.",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        help_text="Amount covered by this receipt (optional).",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Service Receipt",
                "verbose_name_plural": "Service Receipts",
                "ordering": ["created_at"],
            },
        ),
    ]
