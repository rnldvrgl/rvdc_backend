from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("installations", "0024_airconunit_parts_warranty_months"),
    ]

    operations = [
        migrations.AddField(
            model_name="airconmodel",
            name="compressor_warranty_months",
            field=models.PositiveIntegerField(
                default=60,
                help_text="Compressor warranty duration in months (default: 60 = 5 years)",
            ),
        ),
    ]
