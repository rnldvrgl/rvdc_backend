# Generated manually to remove StockTransfer dependency

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0006_alter_expense_transfer'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='expense',
            name='transfer',
        ),
    ]
