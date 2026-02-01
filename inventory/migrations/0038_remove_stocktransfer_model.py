# Generated manually to remove StockTransfer model
# No existing data in production, safe to delete

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0035_remove_seed_stalls'),
        ('expenses', '0007_remove_expense_transfer'),  # Must remove FK first
    ]

    operations = [
        migrations.DeleteModel(
            name='StockTransferItem',
        ),
        migrations.DeleteModel(
            name='StockTransfer',
        ),
    ]
