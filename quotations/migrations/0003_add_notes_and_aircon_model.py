import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("installations", "0001_initial"),
        ("quotations", "0002_add_signature_name_date_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="notes",
            field=models.TextField(
                blank=True,
                help_text="Notes displayed below items before subtotal (e.g. warranty info)",
            ),
        ),
        migrations.AddField(
            model_name="quotationitem",
            name="aircon_model",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="installations.airconmodel",
                help_text="Optional link to an aircon model for this line item",
            ),
        ),
    ]
