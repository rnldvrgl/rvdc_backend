# Generated migration to remove recurring expense fields

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0010_alter_expense_payment_method'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='expense',
            name='recurring',
        ),
        migrations.RemoveField(
            model_name='expense',
            name='recurring_frequency',
        ),
    ]
