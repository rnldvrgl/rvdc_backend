from django.db import migrations


def seed_system_stalls(apps, schema_editor):
    Stall = apps.get_model("inventory", "Stall")

    # Helper to get or create stall by name (case-sensitive), excluding soft-deleted
    def ensure_stall(
        name: str, location: str, inventory_enabled: bool, is_system: bool
    ):
        # Try to find an active stall with this name
        stall = Stall.objects.filter(name=name, is_deleted=False).first()
        if stall is None:
            stall = Stall.objects.create(
                name=name,
                location=location,
                inventory_enabled=inventory_enabled,
                is_system=is_system,
            )
        else:
            # Update flags to enforce system-managed behavior
            updated = False
            if stall.location != location:
                stall.location = location
                updated = True
            if stall.inventory_enabled != inventory_enabled:
                stall.inventory_enabled = inventory_enabled
                updated = True
            if stall.is_system != is_system:
                stall.is_system = is_system
                updated = True
            if updated:
                stall.save(
                    update_fields=[
                        "location",
                        "inventory_enabled",
                        "is_system",
                        "updated_at",
                    ]
                )
        return stall

    # Seed the two system-managed stalls:
    # - Main (Service): not inventory owner, read-only system stall
    # - Sub (Parts): inventory owner, single source-of-truth for stock
    ensure_stall(
        name="Main", location="Service", inventory_enabled=False, is_system=True
    )
    ensure_stall(name="Sub", location="Parts", inventory_enabled=True, is_system=True)


def unseed_system_stalls(apps, schema_editor):
    """
    Reverse operation: convert the system flags back to non-system stalls.
    We do NOT delete records to avoid data loss.
    """
    Stall = apps.get_model("inventory", "Stall")
    for name in ("Main", "Sub"):
        stall = Stall.objects.filter(name=name, is_deleted=False).first()
        if stall and stall.is_system:
            stall.is_system = False
            stall.save(update_fields=["is_system", "updated_at"])


class Migration(migrations.Migration):
    # Adjust this dependency to the latest migration in your inventory app if needed.
    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_system_stalls, unseed_system_stalls),
    ]
