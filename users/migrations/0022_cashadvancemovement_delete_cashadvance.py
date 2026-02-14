# Generated manually

from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_cash_advances(apps, schema_editor):
    """Migrate existing CashAdvance records to CashAdvanceMovement as debit movements."""
    CashAdvance = apps.get_model('users', 'CashAdvance')
    CashAdvanceMovement = apps.get_model('users', 'CashAdvanceMovement')

    movements = []
    for ca in CashAdvance.objects.all().iterator(chunk_size=500):
        movements.append(CashAdvanceMovement(
            employee_id=ca.employee_id,
            movement_type='debit',
            amount=ca.amount,
            balance_after=Decimal('0'),  # Will be recalculated below
            date=ca.date,
            description=ca.reason or 'Cash advance (migrated)',
            reference='migrated',
            created_by_id=ca.created_by_id,
            is_deleted=ca.is_deleted,
        ))
    if movements:
        CashAdvanceMovement.objects.bulk_create(movements, batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0021_customuser_has_cash_ban'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CashAdvanceMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('movement_type', models.CharField(
                    choices=[('credit', 'Credit (+)'), ('debit', 'Debit (-)')],
                    help_text='Credit (+) adds to balance, Debit (-) deducts from balance',
                    max_length=10,
                )),
                ('amount', models.DecimalField(
                    decimal_places=2,
                    help_text='Amount of the movement (always positive, sign determined by movement_type)',
                    max_digits=10,
                )),
                ('balance_after', models.DecimalField(
                    decimal_places=2,
                    default=0,
                    help_text="Snapshot of the employee's cash ban balance after this movement",
                    max_digits=10,
                )),
                ('date', models.DateField(help_text='Date of the movement')),
                ('description', models.TextField(
                    blank=True,
                    help_text="Notes or reason for the movement",
                )),
                ('reference', models.CharField(
                    blank=True,
                    help_text="Optional reference (e.g., 'payroll-123', 'manual')",
                    max_length=100,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(
                    help_text='User who recorded this movement',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_cash_advance_movements',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('employee', models.ForeignKey(
                    help_text='Employee whose cash ban balance is affected',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cash_advance_movements',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-date', '-created_at'],
                'indexes': [
                    models.Index(fields=['employee', 'date'], name='users_cashad_employe_idx'),
                    models.Index(fields=['-date'], name='users_cashad_date_idx'),
                    models.Index(fields=['employee', 'movement_type'], name='users_cashad_emp_type_idx'),
                ],
            },
        ),
        migrations.RunPython(migrate_cash_advances, migrations.RunPython.noop),
        migrations.DeleteModel(name='CashAdvance'),
    ]
