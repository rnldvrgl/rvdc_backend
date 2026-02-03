from django.db import migrations


def unseed_stalls(apps, schema_editor):
    Stall = apps.get_model("inventory", "Stall")
    for name, location in [
        ("Main", "Services"),
        ("Sub", "Parts")
    ]:
        stall = Stall.objects.filter(name=name, location=location).first()
        if stall:
            stall.delete()

class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0034_stall_inventory_enabled_stall_is_system'),
    ]

    operations = [
        migrations.RunPython(unseed_stalls),
    ]
