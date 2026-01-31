# Generated migration file for TaxBracket and PercentageDeduction models

from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('payroll', '0011_manualdeduction'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaxBracket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('min_income', models.DecimalField(decimal_places=2, help_text='Minimum weekly income for this bracket (inclusive)', max_digits=12)),
                ('max_income', models.DecimalField(blank=True, decimal_places=2, help_text='Maximum weekly income for this bracket (inclusive). Null = no upper limit', max_digits=12, null=True)),
                ('base_tax', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Base tax amount for this bracket', max_digits=12)),
                ('rate', models.DecimalField(decimal_places=4, help_text='Tax rate as decimal (e.g., 0.20 for 20%)', max_digits=5)),
                ('effective_start', models.DateField(help_text='Date this bracket becomes effective')),
                ('effective_end', models.DateField(blank=True, help_text='Date this bracket stops being effective. Null = still active', null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_tax_brackets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['min_income'],
            },
        ),
        migrations.CreateModel(
            name='PercentageDeduction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('deduction_type', models.CharField(choices=[('withholding_tax', 'Withholding Tax'), ('hdmf_savings', 'HDMF Savings'), ('custom_percent', 'Custom Percentage')], max_length=30)),
                ('rate', models.DecimalField(decimal_places=4, help_text='Rate as decimal (e.g., 0.05 for 5%)', max_digits=5)),
                ('description', models.TextField(blank=True)),
                ('effective_start', models.DateField()),
                ('effective_end', models.DateField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_percentage_deductions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='taxbracket',
            index=models.Index(fields=['effective_start', 'is_active'], name='payroll_tax_effecti_idx'),
        ),
        migrations.AddIndex(
            model_name='percentagededuction',
            index=models.Index(fields=['deduction_type', 'is_active'], name='payroll_per_deducti_idx'),
        ),
        migrations.AddIndex(
            model_name='percentagededuction',
            index=models.Index(fields=['effective_start'], name='payroll_per_effecti_idx'),
        ),
    ]
