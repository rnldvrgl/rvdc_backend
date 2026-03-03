from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0023_add_is_pending_to_cash_advance_movement"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
