# Generated manually on 2026-04-07

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0059_asset_sale_client_fk'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceExtraCharge',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(help_text="Description of the charge (e.g. 'Dismantle Fee', 'Site Survey')", max_length=255)),
                ('amount', models.DecimalField(decimal_places=2, help_text='Charge amount in PHP', max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('service', models.ForeignKey(
                    help_text='Service this charge belongs to',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='extra_charges',
                    to='services.service',
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    help_text='User who added this charge',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='service_extra_charges_created',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Service Extra Charge',
                'verbose_name_plural': 'Service Extra Charges',
                'ordering': ['created_at'],
            },
        ),
    ]
