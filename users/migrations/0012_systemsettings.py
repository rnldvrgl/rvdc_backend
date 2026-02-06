# Generated manually on 2026-02-07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0011_add_payroll_and_benefits_flags'),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('birthday_greeting_enabled', models.BooleanField(default=True, help_text='Enable/disable birthday greeting modal')),
                ('birthday_greeting_title', models.CharField(default='Happy Birthday!', help_text='Title for birthday greeting modal', max_length=100)),
                ('birthday_greeting_message', models.TextField(default='Wishing you a wonderful day filled with happiness and joy! Thank you for being part of our team.', help_text='Message shown in birthday greeting modal')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'System Settings',
                'verbose_name_plural': 'System Settings',
            },
        ),
    ]
