from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TimeEntry",
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
                ("clock_in", models.DateTimeField()),
                ("clock_out", models.DateTimeField()),
                ("unpaid_break_minutes", models.PositiveIntegerField(default=0)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("manual", "Manual"),
                            ("schedule", "From Schedule"),
                            ("import", "Imported"),
                        ],
                        default="manual",
                        max_length=20,
                    ),
                ),
                (
                    "approved",
                    models.BooleanField(
                        default=True,
                        help_text="Only approved entries are included in payroll computations.",
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="time_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-clock_in"],
            },
        ),
        migrations.AddIndex(
            model_name="timeentry",
            index=models.Index(
                fields=["employee", "clock_in"], name="timeentry_emp_clock_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="timeentry",
            index=models.Index(fields=["clock_in"], name="timeentry_clock_idx"),
        ),
        migrations.AddIndex(
            model_name="timeentry",
            index=models.Index(fields=["approved"], name="timeentry_appr_idx"),
        ),
        migrations.CreateModel(
            name="WeeklyPayroll",
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
                    "week_start",
                    models.DateField(
                        help_text="Start date of the payroll week (recommended: Monday)."
                    ),
                ),
                ("hourly_rate", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "overtime_threshold",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("40.00"), max_digits=5
                    ),
                ),
                (
                    "overtime_multiplier",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("1.50"), max_digits=4
                    ),
                ),
                (
                    "regular_hours",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=6
                    ),
                ),
                (
                    "overtime_hours",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=6
                    ),
                ),
                (
                    "allowances",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=10
                    ),
                ),
                (
                    "gross_pay",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=12
                    ),
                ),
                (
                    "deductions",
                    models.JSONField(
                        default=dict,
                        help_text='Map of deduction name -> amount. Example: {"Tax": 120.55, "Benefits": 35.00}',
                    ),
                ),
                (
                    "total_deductions",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=12
                    ),
                ),
                (
                    "net_pay",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=12
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("approved", "Approved"),
                            ("paid", "Paid"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="weekly_payrolls",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-week_start", "employee_id"],
                "unique_together": {("employee", "week_start")},
            },
        ),
        migrations.AddIndex(
            model_name="weeklypayroll",
            index=models.Index(
                fields=["employee", "week_start"], name="weeklypayroll_emp_week_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="weeklypayroll",
            index=models.Index(fields=["status"], name="weeklypayroll_status_idx"),
        ),
    ]
