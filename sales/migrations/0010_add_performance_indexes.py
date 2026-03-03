# Generated manually for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0009_merge_20251204_0617"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="salestransaction",
            index=models.Index(
                fields=["payment_status"], name="sales_payment_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="salestransaction",
            index=models.Index(
                fields=["created_at"], name="sales_created_at_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="salestransaction",
            index=models.Index(
                fields=["stall", "created_at"], name="sales_stall_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="salestransaction",
            index=models.Index(
                fields=["is_deleted"], name="sales_is_deleted_idx"
            ),
        ),
    ]
