from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0030_systemsettings_google_sheets_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemsettings",
            name="google_sheets_main_spreadsheet_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Main-stall monthly Google Spreadsheet ID from the sheet URL",
                max_length=255,
            ),
        ),
    ]
