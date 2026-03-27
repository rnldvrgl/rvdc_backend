from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="authsession",
            name="access_jti",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(fields=["access_jti"], name="authenticati_access__jti_idx"),
        ),
    ]
