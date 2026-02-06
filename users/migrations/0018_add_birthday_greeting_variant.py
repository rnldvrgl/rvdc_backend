# Generated migration to add birthday_greeting_variant field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0017_remove_birthday_greeting_show_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='birthday_greeting_variant',
            field=models.CharField(
                choices=[
                    ('default', 'Default'),
                    ('minimalist', 'Modern Minimalist'),
                    ('celebration', 'Celebration Theme'),
                    ('elegant', 'Elegant Professional'),
                    ('playful', 'Playful & Fun'),
                ],
                default='default',
                help_text='Design variant for birthday greeting card',
                max_length=20
            ),
        ),
    ]
