# Generated manually for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0039_add_stall_identification"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="stock",
            index=models.Index(
                fields=["item", "stall"], name="stock_item_stall_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="stock",
            index=models.Index(
                fields=["is_deleted"], name="stock_is_deleted_idx"
            ),
        ),
    ]
