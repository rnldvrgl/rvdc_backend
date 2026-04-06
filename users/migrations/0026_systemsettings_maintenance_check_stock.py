from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0025_add_e_signature'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='maintenance_mode',
            field=models.BooleanField(
                default=False,
                help_text='Enable maintenance mode — non-admin users will see the maintenance screen',
            ),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='check_stock_on_sale',
            field=models.BooleanField(
                default=True,
                help_text='Check and deduct stock when creating or editing a sales transaction',
            ),
        ),
    ]
