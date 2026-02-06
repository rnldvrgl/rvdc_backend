# Generated manually on 2026-02-07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_systemsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='birthday_greeting_button_text',
            field=models.CharField(default='Thank You! 💝', help_text='Text shown on the dismiss button', max_length=50),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='birthday_greeting_show_confetti',
            field=models.BooleanField(default=True, help_text='Show animated confetti on birthday greeting'),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='birthday_greeting_show_emojis',
            field=models.BooleanField(default=True, help_text='Show emoji decorations on birthday greeting'),
        ),
    ]
