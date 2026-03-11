from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0011_add_cheque_collection_to_payments"),
        ("services", "0029_add_cheque_collection_to_payments"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="related_sub_transaction",
            field=models.ForeignKey(
                blank=True,
                help_text="Sub stall sales transaction for parts revenue tracking",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sub_stall_services",
                to="sales.salestransaction",
            ),
        ),
    ]
