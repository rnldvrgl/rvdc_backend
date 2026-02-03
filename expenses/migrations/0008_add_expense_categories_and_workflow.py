# Generated migration for simplified expense system

from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0001_initial'),
        ('expenses', '0007_remove_expense_transfer'),
    ]

    operations = [
        # Create ExpenseCategory model
        migrations.CreateModel(
            name='ExpenseCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('monthly_budget', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Monthly budget allocated for this category', max_digits=12)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subcategories', to='expenses.expensecategory')),
            ],
            options={
                'verbose_name': 'Expense Category',
                'verbose_name_plural': 'Expense Categories',
                'ordering': ['name'],
            },
        ),

        # Add new fields to Expense model
        migrations.AddField(
            model_name='expense',
            name='category',
            field=models.ForeignKey(blank=True, help_text='Expense category for organization and budgeting', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='expenses', to='expenses.expensecategory'),
        ),
        migrations.AddField(
            model_name='expense',
            name='expense_date',
            field=models.DateField(default=django.utils.timezone.now, help_text='Date when expense was incurred'),
        ),
        migrations.AddField(
            model_name='expense',
            name='reference_number',
            field=models.CharField(blank=True, help_text='Invoice number, receipt number, or other reference', max_length=100),
        ),
        migrations.AddField(
            model_name='expense',
            name='vendor',
            field=models.CharField(blank=True, help_text='Vendor or supplier name', max_length=255),
        ),
        migrations.AddField(
            model_name='expense',
            name='payment_status',
            field=models.CharField(choices=[('unpaid', 'Unpaid'), ('partial', 'Partially Paid'), ('paid', 'Fully Paid')], default='unpaid', max_length=20),
        ),
        migrations.AddField(
            model_name='expense',
            name='payment_method',
            field=models.CharField(blank=True, help_text='Cash, Bank Transfer, Cheque, etc.', max_length=50),
        ),
        migrations.AddField(
            model_name='expense',
            name='recurring',
            field=models.BooleanField(default=False, help_text='Is this a recurring expense?'),
        ),
        migrations.AddField(
            model_name='expense',
            name='recurring_frequency',
            field=models.CharField(blank=True, choices=[('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly'), ('quarterly', 'Quarterly'), ('yearly', 'Yearly')], max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='expense',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),

        # Update total_price field to support larger amounts
        migrations.AlterField(
            model_name='expense',
            name='total_price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AlterField(
            model_name='expense',
            name='paid_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),

        # Update ExpenseItem fields
        migrations.AddField(
            model_name='expenseitem',
            name='description',
            field=models.CharField(default='', help_text='Description of the expense item', max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='expenseitem',
            name='unit_price',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10),
        ),
        migrations.AddField(
            model_name='expenseitem',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='expenseitem',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='expenseitem',
            name='quantity',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name='expenseitem',
            name='item',
            field=models.ForeignKey(blank=True, help_text='Link to inventory item if applicable', null=True, on_delete=django.db.models.deletion.CASCADE, to='inventory.item'),
        ),

        # Add indexes for ExpenseCategory
        migrations.AddIndex(
            model_name='expensecategory',
            index=models.Index(fields=['is_active', 'is_deleted'], name='expenses_ex_is_acti_8b5c3f_idx'),
        ),

        # Add indexes for Expense
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(fields=['stall', 'expense_date'], name='expenses_ex_stall_i_a1b2c3_idx'),
        ),
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(fields=['category', 'expense_date'], name='expenses_ex_categor_d4e5f6_idx'),
        ),
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(fields=['payment_status', 'expense_date'], name='expenses_ex_payment_j1k2l3_idx'),
        ),
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(fields=['is_deleted'], name='expenses_ex_is_dele_m4n5o6_idx'),
        ),
    ]
