from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0029_add_notification_sound"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemsettings",
            name="google_service_account_json",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Service account JSON credentials content used for Google Sheets API",
            ),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="google_sheets_spreadsheet_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Google Spreadsheet ID from the sheet URL",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="google_sheets_sub_stall_type",
            field=models.CharField(
                blank=True,
                default="sub",
                help_text="Only transactions from this stall_type are synced (e.g. sub)",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="google_sheets_sync_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Enable automatic sync of sub-stall sales transactions to Google Sheets",
            ),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="google_sheets_worksheet_name",
            field=models.CharField(
                blank=True,
                default="Sub Stall Sales",
                help_text="Worksheet/tab name where synced rows are written",
                max_length=100,
            ),
        ),
    ]
