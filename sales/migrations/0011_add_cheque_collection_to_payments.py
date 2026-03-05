# Generated manually
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('receivables', '0001_initial'),
        ('sales', '0010_add_performance_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='salespayment',
            name='cheque_collection',
            field=models.ForeignKey(
                blank=True,
                help_text='Linked cheque collection if payment type is cheque',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sales_payments',
                to='receivables.chequecollection'
            ),
        ),
    ]
