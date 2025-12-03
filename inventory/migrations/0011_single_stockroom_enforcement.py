from django.core.exceptions import ValidationError
from django.db import migrations


def enforce_single_stockroom(apps, schema_editor):
    """
    Validates that:
    - Only the Sub (Parts) system stall has tracked Stock rows.
    - StockRoomStock is the single source of truth (no tracked stock outside Sub).

    If violations are found, raise ValidationError to stop the migration and surface
    corrective instructions.
    """
    Stall = apps.get_model("inventory", "Stall")
    Stock = apps.get_model("inventory", "Stock")
    StockRoomStock = apps.get_model("inventory", "StockRoomStock")

    # Identify the Sub (Parts) stall that should be system-managed and the only inventory owner.
    sub_stall = (
        Stall.objects.filter(
            name="Sub",
            location="Parts",
            is_system=True,
            is_deleted=False,
            inventory_enabled=True,
        )
        .order_by("id")
        .first()
    )

    if sub_stall is None:
        raise ValidationError(
            "Single stockroom enforcement failed: System Sub (Parts) stall not found. "
            "Ensure a stall exists with name='Sub', location='Parts', is_system=True, "
            "inventory_enabled=True, and is_deleted=False."
        )

    # 1) Ensure no tracked stock exists outside Sub (Parts) stall
    invalid_stock_qs = Stock.objects.filter(
        is_deleted=False,
        track_stock=True,
    ).exclude(stall_id=sub_stall.id)

    invalid_count = invalid_stock_qs.count()
    if invalid_count > 0:
        # Provide a succinct list of offenders to help correction
        offenders = list(
            invalid_stock_qs.values_list("id", "stall__name", "stall__location")[:25]
        )
        raise ValidationError(
            {
                "detail": (
                    f"Found {invalid_count} tracked Stock rows outside the Sub (Parts) stall. "
                    "Move quantities back to the stock room or transfer to the Sub stall to proceed."
                ),
                "first_25_offenders": offenders,
            }
        )

    # 2) Ensure all StockRoomStock items are consistent:
    #    There should be exactly one stock room entry per item (already enforced by UniqueConstraint).
    #    Validate non-negative quantities and thresholds.
    negatives_qs = StockRoomStock.objects.filter(is_deleted=False).filter(
        models.Q(quantity__lt=0) | models.Q(low_stock_threshold__lt=0)
    )
    negatives_count = negatives_qs.count()
    if negatives_count > 0:
        offenders = list(negatives_qs.values_list("id", "item__name")[:25])
        raise ValidationError(
            {
                "detail": (
                    f"Found {negatives_count} StockRoomStock rows with negative values. "
                    "Fix quantity and low_stock_threshold to be non-negative."
                ),
                "first_25_offenders": offenders,
            }
        )

    # 3) Optional sanity check: confirm that Sub stall has inventory_enabled=True and is_system=True
    if not sub_stall.inventory_enabled or not sub_stall.is_system:
        raise ValidationError(
            "Sub (Parts) stall flags are incorrect. Expected inventory_enabled=True and is_system=True."
        )

    # If we reached here, the dataset satisfies single stockroom enforcement.
    # No data changes are performed by this migration (validation-only).


def reverse_noop(apps, schema_editor):
    # This migration is validation-only; no reverse action necessary.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0010_seed_system_stalls"),
    ]

    operations = [
        migrations.RunPython(enforce_single_stockroom, reverse_noop),
    ]
