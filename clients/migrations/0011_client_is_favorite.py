from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0010_make_province_city_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="is_favorite",
            field=models.BooleanField(default=False),
        ),
    ]
