import decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0044_stockrequest'),
    ]

    operations = [
        migrations.AlterField(
            model_name='item',
            name='retail_price',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(decimal.Decimal('0'))],
            ),
        ),
        migrations.AlterField(
            model_name='item',
            name='wholesale_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(decimal.Decimal('0'))],
            ),
        ),
        migrations.AlterField(
            model_name='item',
            name='technician_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(decimal.Decimal('0'))],
            ),
        ),
        migrations.AlterField(
            model_name='item',
            name='cost_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(decimal.Decimal('0'))],
            ),
        ),
    ]
