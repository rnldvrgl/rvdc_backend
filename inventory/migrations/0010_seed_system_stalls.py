from django.db import migrations


def seed_system_stalls(apps, schema_editor):
    Stall = apps.get_model("inventory", "Stall")

    def ensure_stall(
        name: str, location: str, inventory_enabled: bool, is_system: bool
    ):
        # Determine available fields on Stall to avoid passing unknown kwargs
        field_names = {f.name for f in Stall._meta.get_fields()}
        create_kwargs = {"name": name, "location": location}
        if "inventory_enabled" in field_names:
            create_kwargs["inventory_enabled"] = inventory_enabled
        if "is_system" in field_names:
            create_kwargs["is_system"] = is_system

        # Try to find an active stall with this name

        stall = Stall.objects.filter(name=name, is_deleted=False).first()

        if stall is None:
            # Create with only supported fields
            stall = Stall.objects.create(**create_kwargs)

        else:
            # Update flags to enforce system-managed behavior, only if fields exist

            updated = False

            if getattr(stall, "location", None) != location:
                stall.location = location

                updated = True

            if (
                "inventory_enabled" in field_names
                and getattr(stall, "inventory_enabled", None) != inventory_enabled
            ):
                stall.inventory_enabled = inventory_enabled

                updated = True

            if (
                "is_system" in field_names
                and getattr(stall, "is_system", None) != is_system
            ):
                stall.is_system = is_system

                updated = True

            if updated:
                update_fields = ["location"]
                if "inventory_enabled" in field_names:
                    update_fields.append("inventory_enabled")
                if "is_system" in field_names:
                    update_fields.append("is_system")
                update_fields.append("updated_at")
                stall.save(update_fields=update_fields)
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
