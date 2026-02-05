# Generated manually for analytics calendar events

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CalendarEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, null=True)),
                ('event_date', models.DateField()),
                ('event_type', models.CharField(
                    choices=[
                        ('holiday', 'Holiday'),
                        ('meeting', 'Meeting'),
                        ('maintenance', 'Maintenance'),
                        ('training', 'Training'),
                        ('deadline', 'Deadline'),
                        ('other', 'Other')
                    ],
                    default='other',
                    max_length=20
                )),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='calendar_events',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'db_table': 'calendar_events',
                'ordering': ['-event_date', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='calendarevent',
            index=models.Index(fields=['event_date'], name='calendar_ev_event_d_idx'),
        ),
        migrations.AddIndex(
            model_name='calendarevent',
            index=models.Index(fields=['event_type'], name='calendar_ev_event_t_idx'),
        ),
        migrations.AddIndex(
            model_name='calendarevent',
            index=models.Index(fields=['is_deleted'], name='calendar_ev_is_dele_idx'),
        ),
    ]
