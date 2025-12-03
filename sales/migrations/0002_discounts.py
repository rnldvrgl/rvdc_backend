from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="salestransaction",
            name="order_discount_rate",
            field=models.DecimalField(
                default=0,
                max_digits=5,
                decimal_places=2,
                help_text="Order-level discount rate (0.00 - 1.00).",
            ),
        ),
        migrations.AddField(
            model_name="salesitem",
            name="line_discount_rate",
            field=models.DecimalField(
                default=0,
                max_digits=5,
                decimal_places=2,
                help_text="Line-level discount rate (0.00 - 1.00).",
            ),
        ),
    ]
