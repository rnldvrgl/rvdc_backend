from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("installations", "0022_airconunit_labor_warranty_months"),
    ]

    operations = [
        migrations.AddField(
            model_name="airconunit",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="airconunit",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="airconunit",
            options={"ordering": ["-created_at"]},
        ),
    ]
