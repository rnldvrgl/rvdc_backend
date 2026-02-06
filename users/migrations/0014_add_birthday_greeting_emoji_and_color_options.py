# Generated manually on 2026-02-07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_add_birthday_greeting_design_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='birthday_greeting_emojis',
            field=models.CharField(default='🎈,🎊,🎁,🎉,🎈', help_text='Comma-separated list of emojis to display (e.g., 🎈,🎊,🎁,🎉,🍺,🎂)', max_length=200),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='birthday_greeting_male_color',
            field=models.CharField(default='from-blue-600 via-purple-600 to-indigo-600', help_text='Tailwind gradient classes for male birthday greeting', max_length=50),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='birthday_greeting_female_color',
            field=models.CharField(default='from-purple-600 via-pink-600 to-blue-600', help_text='Tailwind gradient classes for female birthday greeting', max_length=50),
        ),
    ]
