from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0003_calendarevent_deleted_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calendarevent',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('birthday', 'Birthday'),
                    ('meeting', 'Meeting'),
                    ('maintenance', 'Maintenance'),
                    ('training', 'Training'),
                    ('deadline', 'Deadline'),
                    ('other', 'Other'),
                ],
                default='other',
                max_length=20,
            ),
        ),
    ]
