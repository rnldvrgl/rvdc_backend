from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quotations", "0006_quotationpayment_add_method_ref_si"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="quotation_type",
            field=models.CharField(
                choices=[("standard", "Standard"), ("price_list", "Price List")],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="quotationitem",
            name="promo_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Promotional / discounted price (used in price_list quotations)",
                max_digits=10,
                null=True,
            ),
        ),
    ]
