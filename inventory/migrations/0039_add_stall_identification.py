# Generated manually for two-stall architecture implementation

from django.db import migrations, models


def seed_main_sub_stalls(apps, schema_editor):
    """
    Seed or update Main and Sub stalls for the two-stall architecture.
    - Main stall: handles services and aircon unit sales/installations
    - Sub stall: handles parts inventory (already exists as "Sub" / "Parts")
    """
    Stall = apps.get_model('inventory', 'Stall')

    # 1. Update existing Sub (Parts) stall
    sub_stall = Stall.objects.filter(
        name='Sub',
        location='Parts'
    ).first()

    if sub_stall:
        # Update existing Sub stall with new type
        sub_stall.inventory_enabled = True
        sub_stall.is_system = True
        sub_stall.stall_type = 'sub'
        sub_stall.save()
        print(f"✓ Updated existing Sub stall (ID: {sub_stall.id})")
    else:
        # Create Sub stall if it doesn't exist
        sub_stall = Stall.objects.create(
            name='Sub',
            location='Parts',
            inventory_enabled=True,
            is_system=True,
            stall_type='sub',
        )
        print(f"✓ Created new Sub stall (ID: {sub_stall.id})")

    # 2. Create or update Main stall
    main_stall = Stall.objects.filter(
        name='Main',
        location='Services'
    ).first()

    if main_stall:
        # Update existing Main stall
        main_stall.inventory_enabled = False  # Main doesn't use Stock table
        main_stall.is_system = True
        main_stall.stall_type = 'main'
        main_stall.save()
        print(f"✓ Updated existing Main stall (ID: {main_stall.id})")
    else:
        # Create Main stall
        main_stall = Stall.objects.create(
            name='Main',
            location='Services',
            inventory_enabled=False,  # Main tracks units separately
            is_system=True,
            stall_type='main',
        )
        print(f"✓ Created new Main stall (ID: {main_stall.id})")

    # 3. Update any other existing stalls to have stall_type='other'
    other_stalls = Stall.objects.exclude(
        id__in=[sub_stall.id, main_stall.id]
    ).filter(stall_type='other')  # Only update those not already set

    count = other_stalls.count()
    if count > 0:
        other_stalls.update(
            is_system=False,
            stall_type='other'
        )
        print(f"✓ Updated {count} other stalls to type 'other'")


def reverse_seed(apps, schema_editor):
    """
    Reverse migration: reset stall_type to 'other' for all stalls.
    Note: We don't delete stalls as they may have related data.
    """
    Stall = apps.get_model('inventory', 'Stall')

    # Reset all stalls to default values
    Stall.objects.all().update(stall_type='other')
    print("✓ Reset all stalls to default stall_type='other'")


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0038_remove_stocktransfer_model'),
    ]

    operations = [
        # Add stall_type field
        migrations.AddField(
            model_name='stall',
            name='stall_type',
            field=models.CharField(
                choices=[
                    ('main', 'Main Stall'),
                    ('sub', 'Sub Stall'),
                    ('other', 'Other')
                ],
                default='other',
                help_text='Stall type: Main (services + aircon units), Sub (parts), or Other',
                max_length=10,
            ),
        ),
        # Seed Main and Sub stalls
        migrations.RunPython(seed_main_sub_stalls, reverse_seed),
    ]
