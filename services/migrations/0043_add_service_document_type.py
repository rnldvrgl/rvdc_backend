from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0042_add_discount_audit_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="document_type",
            field=models.CharField(
                choices=[("or", "Official Receipt"), ("si", "Sales Invoice")],
                default="or",
                help_text="Whether the manual receipt is an OR (main stall) or SI (sub stall).",
                max_length=2,
            ),
        ),
    ]
