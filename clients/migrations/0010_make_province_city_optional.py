from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0009_add_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="province",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AlterField(
            model_name="client",
            name="city",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
    ]
