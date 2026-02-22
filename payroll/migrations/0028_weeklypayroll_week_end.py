# Generated manually

from django.db import migrations, models


def populate_week_end(apps, schema_editor):
    """Backfill week_end for existing payroll records (week_start + 6 days)."""
    from datetime import timedelta
    WeeklyPayroll = apps.get_model('payroll', 'WeeklyPayroll')
    payrolls_to_update = []
    for payroll in WeeklyPayroll.objects.filter(week_end__isnull=True).iterator(chunk_size=500):
        payroll.week_end = payroll.week_start + timedelta(days=6)
        payrolls_to_update.append(payroll)
    if payrolls_to_update:
        WeeklyPayroll.objects.bulk_update(payrolls_to_update, ['week_end'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0027_alter_additionalearning_category_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='weeklypayroll',
            name='week_end',
            field=models.DateField(
                blank=True,
                help_text='End date of the payroll week (inclusive).',
                null=True,
            ),
        ),
        migrations.RunPython(populate_week_end, migrations.RunPython.noop),
    ]
