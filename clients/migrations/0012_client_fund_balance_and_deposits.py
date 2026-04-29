# Generated manually to keep the local schema in sync when makemigrations is unavailable.

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0011_drop_legacy_is_favorite_column"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="fund_balance",
            field=models.DecimalField(
                default=Decimal("0.00"),
                decimal_places=2,
                help_text="Available client fund balance for service payments",
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.CreateModel(
            name="ClientFundDeposit",
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
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Amount deposited into client fund",
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
                    ),
                ),
                (
                    "deposit_date",
                    models.DateTimeField(default=timezone.now, help_text="Date the fund was received (used for remittance recording)"),
                ),
                (
                    "payment_method",
                    models.CharField(
                        choices=[
                            ("cash", "Cash"),
                            ("gcash", "GCash"),
                            ("debit", "Debit"),
                            ("credit", "Credit"),
                            ("cheque", "Cheque"),
                        ],
                        help_text="How the fund was received",
                        max_length=10,
                    ),
                ),
                ("notes", models.TextField(blank=True, help_text="Notes about this fund deposit (e.g., 50% downpayment for pre-order #123)")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="fund_deposits",
                        to="clients.client",
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who recorded this fund deposit",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="client_fund_deposits_recorded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-deposit_date"],
            },
        ),
        migrations.AddIndex(
            model_name="clientfunddeposit",
            index=models.Index(fields=["client", "-deposit_date"], name="clients_cli_client__7c2f7c_idx"),
        ),
        migrations.AddIndex(
            model_name="clientfunddeposit",
            index=models.Index(fields=["deposit_date"], name="clients_cli_deposit__b2f0c5_idx"),
        ),
    ]
