from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0003_remove_authsession_authenticati_access__jti_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="authsession",
            name="browser_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="authsession",
            name="os_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="authsession",
            name="remember_me",
            field=models.BooleanField(default=True),
        ),
    ]
