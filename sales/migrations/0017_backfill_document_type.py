"""
Backfill document_type on existing SalesTransaction records.

- Transactions on Main Stall (stall_type='main') → document_type='or'
- Transactions on Sub Stall (stall_type='sub') → document_type='si' (already the default)
- with_2307 remains False for all existing records (clerk can retroactively tag)
"""

from django.db import migrations


def backfill_document_type(apps, schema_editor):
    SalesTransaction = apps.get_model("sales", "SalesTransaction")
    Stall = apps.get_model("inventory", "Stall")

    main_stall_ids = list(
        Stall.objects.filter(stall_type="main").values_list("id", flat=True)
    )

    if main_stall_ids:
        SalesTransaction.objects.filter(stall_id__in=main_stall_ids).update(
            document_type="or"
        )


def reverse_backfill(apps, schema_editor):
    SalesTransaction = apps.get_model("sales", "SalesTransaction")
    SalesTransaction.objects.filter(document_type="or").update(document_type="si")


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0016_add_document_type_and_with_2307"),
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_document_type, reverse_backfill),
    ]
