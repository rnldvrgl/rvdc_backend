from django.db import migrations, models


def populate_stream_name(apps, schema_editor):
    """Set stream_name to cam_{pk} for existing rows."""
    CCTVCamera = apps.get_model("surveillance", "CCTVCamera")
    for cam in CCTVCamera.objects.all():
        cam.stream_name = f"cam_{cam.pk}"
        cam.save(update_fields=["stream_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("surveillance", "0002_replace_xmeye_fields_with_stream_url"),
    ]

    operations = [
        # Add field as nullable first so existing rows don't break
        migrations.AddField(
            model_name="cctvcamera",
            name="stream_name",
            field=models.CharField(
                help_text="Stream identifier used in go2rtc, e.g. cam_1, cam_2",
                max_length=100,
                null=True,
            ),
        ),
        # Populate existing rows
        migrations.RunPython(populate_stream_name, migrations.RunPython.noop),
        # Now make it non-nullable and unique
        migrations.AlterField(
            model_name="cctvcamera",
            name="stream_name",
            field=models.CharField(
                help_text="Stream identifier used in go2rtc, e.g. cam_1, cam_2",
                max_length=100,
                unique=True,
            ),
        ),
    ]
