# Generated manually
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('receivables', '0001_initial'),
        ('services', '0028_decimal_quantity_for_items_used'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicepayment',
            name='cheque_collection',
            field=models.ForeignKey(
                blank=True,
                help_text='Linked cheque collection if payment type is cheque',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='service_payments',
                to='receivables.chequecollection'
            ),
        ),
    ]
