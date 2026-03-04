from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("installations", "0015_modelpricehistory"),
    ]

    operations = [
        migrations.AddField(
            model_name="airconmodel",
            name="cost_price",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Dealer/purchase cost price of this aircon model.",
                max_digits=10,
            ),
        ),
    ]
