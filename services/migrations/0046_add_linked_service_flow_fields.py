from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0045_backfill_service_receipts"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="service_leg",
            field=models.CharField(
                choices=[
                    ("single", "Single"),
                    ("dismantle", "Dismantle"),
                    ("reinstall", "Reinstall"),
                ],
                default="single",
                help_text="Leg classification for linked dismantle/reinstall flow.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="linked_parent_service",
            field=models.ForeignKey(
                blank=True,
                help_text="Parent service when this record is an auto-linked follow-up (e.g. reinstall).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="linked_followup_services",
                to="services.service",
            ),
        ),
    ]
