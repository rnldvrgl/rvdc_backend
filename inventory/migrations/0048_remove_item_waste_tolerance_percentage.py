from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0047_item_is_tracked"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="item",
            name="waste_tolerance_percentage",
        ),
    ]
