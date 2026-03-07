from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0012_alter_dailyattendance_attendance_type_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='halfdayschedule',
            name='schedule_type',
            field=models.CharField(
                choices=[('half_day', 'Half Day'), ('shop_closed', 'Shop Closed')],
                default='half_day',
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name='halfdayschedule',
            index=models.Index(fields=['schedule_type'], name='half_day_sc_schedul_idx'),
        ),
    ]
