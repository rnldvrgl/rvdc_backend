from django.db import migrations, models


def backfill_remittance_date(apps, schema_editor):
    """Populate remittance_date from created_at for existing records."""
    RemittanceRecord = apps.get_model("remittances", "RemittanceRecord")
    for record in RemittanceRecord.objects.filter(remittance_date__isnull=True):
        if record.created_at:
            record.remittance_date = record.created_at.date()
            record.save(update_fields=["remittance_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("remittances", "0005_add_manually_adjusted"),
    ]

    operations = [
        # 1. Add the field (nullable initially)
        migrations.AddField(
            model_name="remittancerecord",
            name="remittance_date",
            field=models.DateField(
                null=True, blank=True, help_text="Business date for this remittance"
            ),
        ),
        # 2. Backfill from created_at
        migrations.RunPython(backfill_remittance_date, migrations.RunPython.noop),
        # 3. Remove old unique_together and add new one
        migrations.AlterUniqueTogether(
            name="remittancerecord",
            unique_together={("stall", "remittance_date")},
        ),
    ]
