from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0026_systemsettings_maintenance_check_stock"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="is_technician",
            field=models.BooleanField(
                default=False,
                help_text="Allow this employee to be assigned as a technician in service jobs regardless of their role",
            ),
        ),
    ]
