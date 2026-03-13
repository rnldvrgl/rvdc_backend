import decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0013_remove_expense_is_paid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='expense',
            name='total_price',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(decimal.Decimal('0'))],
            ),
        ),
        migrations.AlterField(
            model_name='expense',
            name='paid_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(decimal.Decimal('0'))],
            ),
        ),
    ]
