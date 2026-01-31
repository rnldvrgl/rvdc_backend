# Generated migration for enhanced expense system

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

        # Create ExpenseBudget model
        migrations.CreateModel(
            name='ExpenseBudget',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.PositiveSmallIntegerField(help_text='Month (1-12)')),
                ('year', models.PositiveIntegerField(help_text='Year')),
                ('budgeted_amount', models.DecimalField(decimal_places=2, help_text='Budgeted amount for this period', max_digits=12)),
                ('notes', models.TextField(blank=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='budgets', to='expenses.expensecategory')),
                ('stall', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expense_budgets', to='inventory.stall')),
            ],
            options={
                'verbose_name': 'Expense Budget',
                'verbose_name_plural': 'Expense Budgets',
                'ordering': ['-year', '-month', 'category__name'],
            },
        ),

        # Create ExpenseAttachment model
        migrations.CreateModel(
            name='ExpenseAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(help_text='Upload receipt, invoice, or supporting document', upload_to='expenses/attachments/%Y/%m/')),
                ('filename', models.CharField(max_length=255)),
                ('file_type', models.CharField(blank=True, max_length=50)),
                ('file_size', models.PositiveIntegerField(blank=True, help_text='File size in bytes', null=True)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('expense', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='expenses.expense')),
                ('uploaded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Expense Attachment',
                'verbose_name_plural': 'Expense Attachments',
                'ordering': ['-uploaded_at'],
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
            name='approval_status',
            field=models.CharField(choices=[('pending', 'Pending Approval'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('cancelled', 'Cancelled')], default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='expense',
            name='payment_status',
            field=models.CharField(choices=[('unpaid', 'Unpaid'), ('partial', 'Partially Paid'), ('paid', 'Fully Paid')], default='unpaid', max_length=20),
        ),
        migrations.AddField(
            model_name='expense',
            name='priority',
            field=models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')], default='medium', max_length=20),
        ),
        migrations.AddField(
            model_name='expense',
            name='payment_method',
            field=models.CharField(blank=True, help_text='Cash, Bank Transfer, Cheque, etc.', max_length=50),
        ),
        migrations.AddField(
            model_name='expense',
            name='submitted_by',
            field=models.ForeignKey(help_text='User who submitted the expense', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='submitted_expenses', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='expense',
            name='approved_by',
            field=models.ForeignKey(blank=True, help_text='User who approved the expense', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_expenses', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='expense',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='expense',
            name='rejection_reason',
            field=models.TextField(blank=True, help_text='Reason for rejection if applicable'),
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

        # Add indexes for ExpenseBudget
        migrations.AddIndex(
            model_name='expensebudget',
            index=models.Index(fields=['stall', 'year', 'month'], name='expenses_ex_stall_i_c4e72a_idx'),
        ),
        migrations.AddIndex(
            model_name='expensebudget',
            index=models.Index(fields=['category', 'year', 'month'], name='expenses_ex_categor_5f3d1b_idx'),
        ),

        # Add unique constraint for ExpenseBudget
        migrations.AddConstraint(
            model_name='expensebudget',
            constraint=models.UniqueConstraint(fields=('stall', 'category', 'month', 'year'), name='unique_stall_category_period'),
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
            index=models.Index(fields=['approval_status', 'expense_date'], name='expenses_ex_approva_g7h8i9_idx'),
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
