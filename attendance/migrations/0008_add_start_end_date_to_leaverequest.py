# Generated migration for adding start_date and end_date to LeaveRequest

from django.db import migrations, models


def populate_start_end_dates(apps, schema_editor):
    """Populate start_date and end_date from existing date field for backward compatibility."""
    LeaveRequest = apps.get_model('attendance', 'LeaveRequest')
    for leave_request in LeaveRequest.objects.all():
        if not leave_request.start_date:
            leave_request.start_date = leave_request.date
        if not leave_request.end_date:
            leave_request.end_date = leave_request.date
        leave_request.save(update_fields=['start_date', 'end_date'])


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0007_alter_dailyattendance_break_hours_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='leaverequest',
            name='start_date',
            field=models.DateField(blank=True, help_text='Start date of the leave period', null=True),
        ),
        migrations.AddField(
            model_name='leaverequest',
            name='end_date',
            field=models.DateField(blank=True, help_text='End date of the leave period (same as start_date for single-day)', null=True),
        ),
        migrations.RunPython(populate_start_end_dates, migrations.RunPython.noop),
    ]
