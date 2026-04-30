# Generated migration for adding per-item discount to QuotationItem

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quotations', '0009_add_stall_to_quotation'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotationitem',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Per-item discount amount', max_digits=10),
        ),
    ]
