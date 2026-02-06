# Generated migration to remove birthday_greeting_show_time field

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0016_update_birthday_greeting_settings'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='systemsettings',
            name='birthday_greeting_show_time',
        ),
    ]
