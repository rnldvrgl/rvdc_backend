from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("surveillance", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(model_name="cctvcamera", name="uid"),
        migrations.RemoveField(model_name="cctvcamera", name="username"),
        migrations.RemoveField(model_name="cctvcamera", name="password"),
        migrations.RemoveField(model_name="cctvcamera", name="channel"),
        migrations.AddField(
            model_name="cctvcamera",
            name="stream_url",
            field=models.CharField(
                default="",
                help_text="Full go2rtc source URL, e.g. dvrip://user:pass@IP:34567?channel=0 or rtsp://user:pass@IP/stream",
                max_length=500,
            ),
            preserve_default=False,
        ),
    ]
