from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inventory", "0049_direct_stock_request"),
        ("sales", "0019_asset_sale_client_fk"),
    ]

    operations = [
        migrations.CreateModel(
            name="StallMonthlySheet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("month_key", models.CharField(help_text="Month key in YYYY-MM format.", max_length=7)),
                ("spreadsheet_id", models.CharField(help_text="Spreadsheet ID from the Google Sheets URL.", max_length=255)),
                (
                    "spreadsheet_url",
                    models.URLField(
                        blank=True,
                        default="",
                        help_text="Canonical spreadsheet URL. Auto-filled from spreadsheet_id when empty.",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="When false, this month record is kept for history but not used for sync.",
                    ),
                ),
                ("shared_ok", models.BooleanField(default=False)),
                ("shared_to_email", models.EmailField(blank=True, default="", max_length=254)),
                ("shared_at", models.DateTimeField(blank=True, null=True)),
                ("share_error", models.TextField(blank=True, default="")),
                ("last_reminder_sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_monthly_sheets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "stall",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="monthly_google_sheets",
                        to="inventory.stall",
                    ),
                ),
            ],
            options={
                "ordering": ["-month_key", "stall_id"],
                "indexes": [
                    models.Index(fields=["month_key"], name="sales_monthly_sheet_month_idx"),
                    models.Index(fields=["stall", "month_key"], name="sales_monthly_sheet_stall_month_idx"),
                    models.Index(fields=["is_active"], name="sales_monthly_sheet_active_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="stallmonthlysheet",
            constraint=models.UniqueConstraint(fields=("stall", "month_key"), name="unique_stall_monthly_sheet"),
        ),
    ]
