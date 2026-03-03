# Generated migration - Add deleted_at field for soft-delete support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0007_alter_client_contact_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
