from django.db import migrations, models


class Migration(migrations.Migration):
    # Adjust the dependency to your latest services migration if needed.
    dependencies = [
        ("services", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceappliance",
            name="labor_is_free",
            field=models.BooleanField(
                default=False,
                help_text="Mark labor for this appliance as free.",
            ),
        ),
        migrations.AddField(
            model_name="applianceitemused",
            name="is_free",
            field=models.BooleanField(
                default=False,
                help_text="Mark this part as free to the customer.",
            ),
        ),
    ]
