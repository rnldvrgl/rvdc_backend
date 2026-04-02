from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0046_add_custom_item_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="is_tracked",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "If True, stock is maintained in inventory. "
                    "If False, this is a catalogue-only / custom item — no stock deducted, "
                    "but pricing is still sourced from this record."
                ),
            ),
        ),
    ]
