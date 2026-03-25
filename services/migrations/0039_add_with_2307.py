"""
Add with_2307 boolean field to Service model.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0038_add_manual_receipt_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="with_2307",
            field=models.BooleanField(
                default=False,
                help_text="Whether this service has an associated BIR Form 2307.",
            ),
        ),
    ]
