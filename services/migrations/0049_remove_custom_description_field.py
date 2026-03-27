# Generated manually on 2026-03-27

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0048_serviceappliance_unit_type_aircon_model'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='applianceitemused',
            name='custom_description',
        ),
        migrations.RemoveField(
            model_name='serviceitemused',
            name='custom_description',
        ),
    ]
