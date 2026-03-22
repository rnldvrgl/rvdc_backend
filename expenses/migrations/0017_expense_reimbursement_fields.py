"""
Add reimbursement tracking fields to Expense model.

Allows expenses to be marked as reimbursable and track
reimbursement status, amount, method, and notes.
"""

import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0016_expense_is_reimbursement'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='is_reimbursable',
            field=models.BooleanField(default=False, help_text='Whether this expense is expected to be reimbursed'),
        ),
        migrations.AddField(
            model_name='expense',
            name='reimbursement_status',
            field=models.CharField(
                choices=[
                    ('not_applicable', 'Not Applicable'),
                    ('pending', 'Pending Reimbursement'),
                    ('partial', 'Partially Reimbursed'),
                    ('reimbursed', 'Fully Reimbursed'),
                ],
                default='not_applicable',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='expense',
            name='reimbursed_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
            ),
        ),
        migrations.AddField(
            model_name='expense',
            name='reimbursed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='expense',
            name='reimbursement_method',
            field=models.CharField(blank=True, help_text='How the reimbursement was received', max_length=50),
        ),
        migrations.AddField(
            model_name='expense',
            name='reimbursement_notes',
            field=models.TextField(blank=True, help_text='Notes about the reimbursement'),
        ),
    ]
