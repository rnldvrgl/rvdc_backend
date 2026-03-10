from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0024_customuser_deleted_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="e_signature",
            field=models.ImageField(blank=True, null=True, upload_to="e_signatures/"),
        ),
    ]
