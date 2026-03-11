# Generated migration for decimal quantity support in sales items

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0010_add_performance_indexes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='salesitem',
            name='quantity',
            field=models.DecimalField(
                decimal_places=2,
                default=1,
                help_text='Quantity sold (supports decimals for kg, ft, etc.)',
                max_digits=10
            ),
        ),
    ]
