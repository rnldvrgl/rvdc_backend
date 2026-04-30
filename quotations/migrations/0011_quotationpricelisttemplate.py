# Generated migration for adding QuotationPriceListTemplate model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quotations', '0010_quotationitem_discount_amount'),
        ('installations', '0001_initial'),  # Adjust as needed
    ]

    operations = [
        migrations.CreateModel(
            name='QuotationPriceListTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Template name (e.g., \'Standard Price List 2024\')', max_length=255)),
                ('description', models.TextField(blank=True, help_text='Description of this price list template')),
                ('is_active', models.BooleanField(default=True, help_text='Whether this template is available for use')),
                ('is_default', models.BooleanField(default=False, help_text='If true, auto-selected when creating a new price list quotation')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('aircon_models', models.ManyToManyField(blank=True, help_text='Aircon models to include in this price list. Leave empty to include all.', related_name='price_list_templates', to='installations.airconmodel')),
            ],
            options={
                'ordering': ['-is_default', 'name'],
            },
        ),
    ]
