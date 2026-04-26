from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0032_systemsettings_sub_stall_unit_revenue_additional"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemsettings",
            name="google_sheets_share_email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Single Google account email to share newly configured monthly sheets with",
                max_length=254,
            ),
        ),
    ]
