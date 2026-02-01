# Generated migration for enhanced schedule model (simplified - no route tracking)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schedules', '0001_initial'),
        ('services', '0012_add_revenue_attribution_and_promos'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('clients', '0001_initial'),
    ]

    operations = [
        # Remove old fields
        migrations.RemoveField(
            model_name='schedule',
            name='scheduled_datetime',
        ),
        migrations.RemoveField(
            model_name='schedule',
            name='service_type',
        ),

        # Add new fields to Schedule
        migrations.AddField(
            model_name='schedule',
            name='service',
            field=models.ForeignKey(
                blank=True,
                help_text='Linked service record',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='schedules',
                to='services.service',
            ),
        ),
        migrations.AddField(
            model_name='schedule',
            name='schedule_type',
            field=models.CharField(
                choices=[
                    ('home_service', 'Home Service'),
                    ('pull_out', 'Pull-Out (Pick-up)'),
                    ('return', 'Return (Delivery)'),
                    ('on_site', 'On-Site Service'),
                ],
                default='home_service',
                help_text='Type of scheduled activity',
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='schedule',
            name='scheduled_date',
            field=models.DateField(
                default='2024-01-01',
                help_text='Date of the scheduled activity',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='schedule',
            name='scheduled_time',
            field=models.TimeField(
                default='09:00:00',
                help_text='Time of the scheduled activity',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='schedule',
            name='estimated_duration',
            field=models.PositiveIntegerField(
                default=60,
                help_text='Estimated duration in minutes',
            ),
        ),
        migrations.AddField(
            model_name='schedule',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('confirmed', 'Confirmed'),
                    ('in_progress', 'In Progress'),
                    ('completed', 'Completed'),
                    ('cancelled', 'Cancelled'),
                    ('rescheduled', 'Rescheduled'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='schedule',
            name='address',
            field=models.TextField(
                blank=True,
                help_text='Service location address (uses client address if not specified)',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='schedule',
            name='contact_person',
            field=models.CharField(
                blank=True,
                help_text='Contact person at location',
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='schedule',
            name='contact_number',
            field=models.CharField(
                blank=True,
                help_text='Contact number for appointment',
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='schedule',
            name='internal_notes',
            field=models.TextField(
                blank=True,
                help_text='Internal notes (not visible to client)',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='schedule',
            name='actual_start_time',
            field=models.DateTimeField(
                blank=True,
                help_text='Actual start time of service',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='schedule',
            name='actual_end_time',
            field=models.DateTimeField(
                blank=True,
                help_text='Actual end time of service',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='schedule',
            name='completed_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='completed_schedules',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='schedule',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='schedule',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_schedules',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # Update existing fields (keep technicians as ManyToMany)
        migrations.AlterField(
            model_name='schedule',
            name='client',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='schedules',
                to='clients.client',
            ),
        ),
        migrations.AlterField(
            model_name='schedule',
            name='technicians',
            field=models.ManyToManyField(
                blank=True,
                limit_choices_to={'role': 'technician', 'is_deleted': False},
                related_name='schedules',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='schedule',
            name='notes',
            field=models.TextField(
                blank=True,
                help_text='Additional notes or instructions',
                null=True,
            ),
        ),

        # Create ScheduleStatusHistory model
        migrations.CreateModel(
            name='ScheduleStatusHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('confirmed', 'Confirmed'),
                        ('in_progress', 'In Progress'),
                        ('completed', 'Completed'),
                        ('cancelled', 'Cancelled'),
                        ('rescheduled', 'Rescheduled'),
                    ],
                    max_length=20,
                )),
                ('notes', models.TextField(
                    blank=True,
                    help_text='Reason for status change',
                    null=True,
                )),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('changed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
                ('schedule', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='status_history',
                    to='schedules.schedule',
                )),
            ],
            options={
                'ordering': ['-changed_at'],
                'verbose_name_plural': 'Schedule Status Histories',
            },
        ),

        # Add indexes
        migrations.AddIndex(
            model_name='schedule',
            index=models.Index(fields=['scheduled_date'], name='schedules_s_schedul_idx'),
        ),
        migrations.AddIndex(
            model_name='schedule',
            index=models.Index(fields=['status'], name='schedules_s_status_idx'),
        ),
        migrations.AddIndex(
            model_name='schedule',
            index=models.Index(fields=['service'], name='schedules_s_service_idx'),
        ),

        # Update Meta
        migrations.AlterModelOptions(
            name='schedule',
            options={'ordering': ['scheduled_date', 'scheduled_time']},
        ),
    ]
