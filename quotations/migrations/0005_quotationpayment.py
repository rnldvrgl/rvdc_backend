from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("quotations", "0004_quotationitem_aircon_unit"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuotationPayment",
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
                    "label",
                    models.CharField(
                        help_text="e.g. '50% Downpayment', '50% Upon Job Completion'",
                        max_length=255,
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(decimal_places=2, max_digits=12),
                ),
                (
                    "payment_date",
                    models.DateField(blank=True, null=True),
                ),
                (
                    "receipt_number",
                    models.CharField(blank=True, max_length=100),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "quotation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payments",
                        to="quotations.quotation",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
