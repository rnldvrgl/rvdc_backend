from django.db import migrations


def backfill_service_receipts(apps, schema_editor):
    """
    For every Service that already has a manual_receipt_number recorded,
    create a corresponding ServiceReceipt row so existing data is preserved
    in the new multi-receipt model.
    """
    Service = apps.get_model("services", "Service")
    ServiceReceipt = apps.get_model("services", "ServiceReceipt")

    receipts_to_create = []
    for svc in Service.objects.filter(
        is_deleted=False,
        manual_receipt_number__isnull=False,
    ).exclude(manual_receipt_number=""):
        receipts_to_create.append(
            ServiceReceipt(
                service=svc,
                receipt_number=svc.manual_receipt_number,
                receipt_book=svc.receipt_book or None,
                document_type=svc.document_type or "or",
                with_2307=svc.with_2307 or False,
                amount=None,  # amount was not tracked per-receipt before
            )
        )

    if receipts_to_create:
        ServiceReceipt.objects.bulk_create(receipts_to_create, ignore_conflicts=True)


def reverse_backfill(apps, schema_editor):
    """Undo: remove all ServiceReceipt rows that were created from Service fields."""
    ServiceReceipt = apps.get_model("services", "ServiceReceipt")
    Service = apps.get_model("services", "Service")

    # Delete only those whose receipt_number matches what's on the service
    service_receipt_pairs = Service.objects.filter(
        manual_receipt_number__isnull=False,
    ).exclude(manual_receipt_number="").values_list("id", "manual_receipt_number")

    for service_id, receipt_number in service_receipt_pairs:
        ServiceReceipt.objects.filter(
            service_id=service_id,
            receipt_number=receipt_number,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0044_add_service_receipt"),
    ]

    operations = [
        migrations.RunPython(backfill_service_receipts, reverse_backfill),
    ]
