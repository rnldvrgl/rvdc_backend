from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("installations", "0012_airconmodel_horsepower"),
    ]

    operations = [
        migrations.AddField(
            model_name="airconmodel",
            name="parts_warranty_months",
            field=models.PositiveIntegerField(
                default=60,
                help_text="Parts (unit) warranty duration in months (default: 60 = 5 years)",
            ),
        ),
        migrations.AddField(
            model_name="airconmodel",
            name="labor_warranty_months",
            field=models.PositiveIntegerField(
                default=12,
                help_text="Labor warranty duration in months (default: 12 = 1 year)",
            ),
        ),
    ]
