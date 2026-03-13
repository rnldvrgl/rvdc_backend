from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0012_expensecategory_deleted_at'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='expense',
            name='is_paid',
        ),
    ]
