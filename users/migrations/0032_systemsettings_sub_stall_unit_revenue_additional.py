from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0031_systemsettings_google_main_spreadsheet"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemsettings",
            name="sub_stall_unit_revenue_additional",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Additional amount per installation unit to shift from main stall to sub stall revenue",
                max_digits=10,
            ),
        ),
    ]
