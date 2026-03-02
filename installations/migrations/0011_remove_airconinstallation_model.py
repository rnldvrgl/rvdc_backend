# Generated migration to remove AirconInstallation model

from django.db import migrations, models
import django.db.models.deletion


def migrate_installation_to_service(apps, schema_editor):
    """
    Migrate AirconUnit.installation FK to installation_service FK.
    Copy service reference from installation to the new foreign key.
    """
    AirconUnit = apps.get_model('installations', 'AirconUnit')
    
    for unit in AirconUnit.objects.select_related('installation').all():
        if unit.installation and unit.installation.service:
            unit.installation_service = unit.installation.service
            unit.save(update_fields=['installation_service'])


class Migration(migrations.Migration):

    dependencies = [
        ('installations', '0010_remove_labor_is_free'),
        ('services', '0001_initial'),  # Ensure Service model exists
    ]

    operations = [
        # Step 1: Add new installation_service FK field (nullable initially)
        migrations.AddField(
            model_name='airconunit',
            name='installation_service',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='installation_units',
                to='services.service',
                help_text='Installation service this unit is part of'
            ),
        ),
        
        # Step 2: Migrate data from installation to installation_service
        migrations.RunPython(
            migrate_installation_to_service,
            reverse_code=migrations.RunPython.noop
        ),
        
        # Step 3: Remove the old installation FK
        migrations.RemoveField(
            model_name='airconunit',
            name='installation',
        ),
        
        # Step 4: Delete AirconInstallation model and related tables
        migrations.DeleteModel(
            name='AirconInstallation',
        ),
        
        migrations.DeleteModel(
            name='AirconItemUsed',
        ),
    ]
