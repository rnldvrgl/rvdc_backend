# Generated manually for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0025_alter_appliancestatushistory_status"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="service",
            index=models.Index(
                fields=["status"], name="service_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="service",
            index=models.Index(
                fields=["payment_status"], name="service_payment_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="service",
            index=models.Index(
                fields=["created_at"], name="service_created_at_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="service",
            index=models.Index(
                fields=["service_type"], name="service_type_idx"
            ),
        ),
    ]
