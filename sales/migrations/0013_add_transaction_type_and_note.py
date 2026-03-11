from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0012_salesitem_decimal_quantity'),
    ]

    operations = [
        migrations.AddField(
            model_name='salestransaction',
            name='transaction_type',
            field=models.CharField(
                choices=[
                    ('sale', 'Sale'),
                    ('replacement', 'Replacement'),
                    ('pull_out', 'Pull Out'),
                ],
                default='sale',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='salestransaction',
            name='note',
            field=models.TextField(blank=True, null=True),
        ),
    ]
