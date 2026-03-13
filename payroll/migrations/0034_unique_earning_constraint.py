from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0033_backfill_is_recurring'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='additionalearning',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_deleted', False)),
                fields=['employee', 'earning_date', 'category'],
                name='unique_earning_per_employee_date_category',
            ),
        ),
    ]
