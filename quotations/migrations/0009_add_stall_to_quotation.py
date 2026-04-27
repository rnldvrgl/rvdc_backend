from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0049_direct_stock_request"),
        ("quotations", "0008_seed_price_list_terms_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="stall",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="quotations",
                to="inventory.stall",
            ),
        ),
    ]
