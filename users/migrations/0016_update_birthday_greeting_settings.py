# Generated migration for birthday greeting settings update

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0015_add_user_gender'),
    ]

    operations = [
        # Remove old color fields
        migrations.RemoveField(
            model_name='systemsettings',
            name='birthday_greeting_male_color',
        ),
        migrations.RemoveField(
            model_name='systemsettings',
            name='birthday_greeting_female_color',
        ),
        # Rename emojis to male_emojis
        migrations.RenameField(
            model_name='systemsettings',
            old_name='birthday_greeting_emojis',
            new_name='birthday_greeting_male_emojis',
        ),
        # Update male_emojis default
        migrations.AlterField(
            model_name='systemsettings',
            name='birthday_greeting_male_emojis',
            field=models.CharField(
                default='🎈,🎊,🎁,🎉,🍺',
                help_text='Comma-separated list of emojis for male employees (e.g., 🎈,🎊,🎁,🎉,🍺)',
                max_length=200
            ),
        ),
        # Add female_emojis field
        migrations.AddField(
            model_name='systemsettings',
            name='birthday_greeting_female_emojis',
            field=models.CharField(
                default='🎈,🎊,🎁,🎉,💐',
                help_text='Comma-separated list of emojis for female employees (e.g., 🎈,🎊,🎁,🎉,💐)',
                max_length=200
            ),
        ),
        # Add show_time field
        migrations.AddField(
            model_name='systemsettings',
            name='birthday_greeting_show_time',
            field=models.BooleanField(
                default=False,
                help_text='Show current time in birthday greeting'
            ),
        ),
    ]
