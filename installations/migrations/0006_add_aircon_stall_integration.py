# Generated migration for aircon unit stall integration

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('installations', '0005_add_warranty_claim_model'),
        ('inventory', '0039_add_stall_identification'),
    ]

    operations = [
        migrations.AddField(
            model_name='airconunit',
            name='stall',
            field=models.ForeignKey(
                blank=True,
                help_text='Main stall that owns this aircon unit',
                limit_choices_to={'is_system': True, 'stall_type': 'main'},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='aircon_units',
                to='inventory.stall',
            ),
        ),
        migrations.AddField(
            model_name='airconunit',
            name='is_sold',
            field=models.BooleanField(
                default=False,
                help_text='Marks if unit has been sold to customer',
            ),
        ),
    ]
