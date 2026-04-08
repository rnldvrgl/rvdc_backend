from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("surveillance", "0003_add_stream_name_field"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cctvCamera",
            name="stream_url",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Full go2rtc source URL (optional — streams are configured directly in go2rtc)",
                max_length=500,
            ),
        ),
    ]
