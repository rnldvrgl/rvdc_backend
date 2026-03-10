from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("installations", "0023_airconunit_soft_delete_and_ordering"),
    ]

    operations = [
        migrations.AddField(
            model_name="airconunit",
            name="parts_warranty_months",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Parts warranty duration in months (overrides model default if set)",
                null=True,
            ),
        ),
    ]
