# Generated migration - Add deleted_at to payroll models for soft-delete support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0029_merge_20260217_1113"),
    ]

    operations = [
        migrations.AddField(
            model_name="additionalearning",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="holiday",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="manualdeduction",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="weeklypayroll",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
