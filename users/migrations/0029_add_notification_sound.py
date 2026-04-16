from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0028_customuser_add_superadmin_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='notification_sound',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Sound file path for push notifications (e.g., /sounds/notification.mp3)',
                max_length=255,
            ),
        ),
    ]
