# Generated migration - Add deleted_at to inventory models for soft-delete support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0040_add_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="productcategory",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="item",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stall",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stock",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stockroomstock",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
