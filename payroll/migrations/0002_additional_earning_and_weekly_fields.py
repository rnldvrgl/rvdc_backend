from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("payroll", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdditionalEarning",
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
                ("earning_date", models.DateField()),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("overtime", "Overtime"),
                            ("installation_pct", "Installation Percentage"),
                            ("custom", "Custom"),
                        ],
                        default="custom",
                        max_length=32,
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=12
                    ),
                ),
                ("description", models.TextField(blank=True)),
                ("reference", models.CharField(blank=True, max_length=100)),
                (
                    "approved",
                    models.BooleanField(
                        default=True,
                        help_text="Only approved additional earnings are included in payroll computations.",
                    ),
                ),
                ("is_deleted", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="additional_earnings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-earning_date"],
            },
        ),
        migrations.AddField(
            model_name="weeklypayroll",
            name="additional_earnings_total",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=12
            ),
        ),
        migrations.AddIndex(
            model_name="additionalsearning",
            index=models.Index(
                fields=["employee", "earning_date"],
                name="additionalearning_emp_date_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="additionalsearning",
            index=models.Index(
                fields=["earning_date"], name="additionalearning_date_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="additionalsearning",
            index=models.Index(fields=["approved"], name="additionalearning_appr_idx"),
        ),
    ]
