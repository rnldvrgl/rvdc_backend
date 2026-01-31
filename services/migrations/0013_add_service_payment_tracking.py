# Generated manually for service payment tracking implementation

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('services', '0012_add_revenue_attribution_and_promos'),
    ]

    operations = [
        # Add payment_status field to Service model
        migrations.AddField(
            model_name='service',
            name='payment_status',
            field=models.CharField(
                choices=[
                    ('unpaid', 'Unpaid'),
                    ('partial', 'Partial'),
                    ('paid', 'Paid'),
                    ('refunded', 'Refunded'),
                ],
                default='unpaid',
                help_text='Payment status of this service',
                max_length=10,
            ),
        ),

        # Create ServicePayment model
        migrations.CreateModel(
            name='ServicePayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payment_type', models.CharField(
                    choices=[
                        ('cash', 'Cash'),
                        ('gcash', 'GCash'),
                        ('credit', 'Credit'),
                        ('debit', 'Debit'),
                        ('cheque', 'Cheque'),
                    ],
                    max_length=10,
                )),
                ('amount', models.DecimalField(
                    decimal_places=2,
                    help_text='Amount paid in this transaction',
                    max_digits=10,
                )),
                ('payment_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('notes', models.TextField(
                    blank=True,
                    help_text='Additional notes about this payment',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('received_by', models.ForeignKey(
                    blank=True,
                    help_text='User who received this payment',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='service_payments_received',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('service', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='payments',
                    to='services.service',
                )),
            ],
            options={
                'verbose_name': 'Service Payment',
                'verbose_name_plural': 'Service Payments',
                'ordering': ['-payment_date'],
            },
        ),
    ]
