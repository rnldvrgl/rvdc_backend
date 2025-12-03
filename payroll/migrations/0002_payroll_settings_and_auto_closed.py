from datetime import time
from decimal import Decimal

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0001_initial"),
    ]

    operations = [
        # Add auto_closed flag to TimeEntry
        migrations.AddField(
            model_name="timeentry",
            name="auto_closed",
            field=models.BooleanField(
                default=False,
                help_text="True if the session was auto-closed at shift end due to missing clock_out.",
            ),
        ),
        # Create PayrollSettings model
        migrations.CreateModel(
            name="PayrollSettings",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "shift_start",
                    models.TimeField(default=time(8, 0)),
                ),
                (
                    "shift_end",
                    models.TimeField(default=time(18, 0)),
                ),
                (
                    "grace_minutes",
                    models.PositiveIntegerField(
                        default=15,
                        help_text="Threshold-only grace minutes for attendance classification.",
                    ),
                ),
                (
                    "auto_close_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Auto-close sessions missing clock_out at shift_end and mark as auto_closed.",
                    ),
                ),
                (
                    "holiday_special_pct",
                    models.DecimalField(
                        max_digits=5,
                        decimal_places=2,
                        default=Decimal("0.30"),
                        help_text="Premium rate for special non-working holidays applied to base daily-rate portion.",
                    ),
                ),
                (
                    "holiday_regular_pct",
                    models.DecimalField(
                        max_digits=5,
                        decimal_places=2,
                        default=Decimal("1.00"),
                        help_text="Premium rate for regular holidays applied to base daily-rate portion.",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
            ],
            options={
                "verbose_name": "Payroll Settings",
                "verbose_name_plural": "Payroll Settings",
            },
        ),
    ]
