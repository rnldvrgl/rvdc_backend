# Generated manually to keep the local schema in sync when makemigrations is unavailable.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("remittances", "0007_add_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="remittancerecord",
            name="total_client_fund_deposits",
            field=models.DecimalField(max_digits=10, decimal_places=2, default=0),
        ),
    ]
