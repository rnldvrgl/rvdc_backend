# Generated manually on 2026-02-05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0010_alter_customuser_profile_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='include_in_payroll',
            field=models.BooleanField(default=True, help_text='Include this employee in payroll generation'),
        ),
        migrations.AddField(
            model_name='customuser',
            name='has_government_benefits',
            field=models.BooleanField(default=True, help_text='Apply government benefits (SSS, PhilHealth, Pag-IBIG, Tax) to this employee'),
        ),
    ]
