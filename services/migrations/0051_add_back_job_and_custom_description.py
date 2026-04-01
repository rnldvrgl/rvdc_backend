# Generated manually on 2026-04-01

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0050_add_job_order_template_print'),
    ]

    operations = [
        # Re-add custom_description to BaseItemUsed subclasses
        migrations.AddField(
            model_name='applianceitemused',
            name='custom_description',
            field=models.CharField(
                blank=True,
                help_text='Name or description for custom items not in inventory.',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='serviceitemused',
            name='custom_description',
            field=models.CharField(
                blank=True,
                help_text='Name or description for custom items not in inventory.',
                max_length=255,
            ),
        ),
        # Back job / re-service fields
        migrations.AddField(
            model_name='service',
            name='is_back_job',
            field=models.BooleanField(
                default=False,
                help_text='Mark as a back job (re-service for a previously completed service)',
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='back_job_parent',
            field=models.ForeignKey(
                blank=True,
                help_text='Original service this back job is for',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='back_jobs',
                to='services.service',
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='back_job_reason',
            field=models.TextField(
                blank=True,
                help_text="Reason for back job (e.g., 'Unit not cooling properly after repair')",
            ),
        ),
    ]
