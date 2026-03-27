from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuthSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("refresh_jti", models.CharField(max_length=64, unique=True)),
                ("device_id", models.CharField(blank=True, default="", max_length=128)),
                ("device_label", models.CharField(blank=True, default="Unknown device", max_length=255)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auth_sessions",
                        to="users.customuser",
                    ),
                ),
            ],
            options={
                "ordering": ["-last_seen_at", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(fields=["user", "is_active"], name="authenticati_user_id_2d2d40_idx"),
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(fields=["device_id"], name="authenticati_device__2f87de_idx"),
        ),
    ]
