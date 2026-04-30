# Generated migration for adding price_list_template to Quotation

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quotations', '0011_quotationpricelisttemplate'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotation',
            name='price_list_template',
            field=models.ForeignKey(blank=True, help_text='Optional price list template (for price_list quotation type)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='quotations', to='quotations.quotationpricelisttemplate'),
        ),
    ]
