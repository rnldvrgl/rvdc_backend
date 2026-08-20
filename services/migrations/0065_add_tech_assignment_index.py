from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("services", "0064_add_indexes"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS services_technician_assignment_tech_idx "
                "ON services_technicianassignment (technician_id);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS services_technician_assignment_tech_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS services_technician_assignment_tech_service_idx "
                "ON services_technicianassignment (technician_id, service_id);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS services_technician_assignment_tech_service_idx;"
            ),
        ),
    ]
