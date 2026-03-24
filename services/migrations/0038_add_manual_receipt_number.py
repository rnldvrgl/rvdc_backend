from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0037_service_items_review_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="manual_receipt_number",
            field=models.CharField(
                blank=True,
                help_text="Official Receipt number for BIR 2307 filing",
                max_length=100,
                null=True,
            ),
        ),
    ]
