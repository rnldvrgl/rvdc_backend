from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("clients", "0013_rename_clients_cli_client__7c2f7c_idx_clients_cli_client__2e35e7_idx_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS clients_created_at_active_idx "
                "ON clients_client (created_at) WHERE is_deleted = false;"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS clients_created_at_active_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS clients_province_city_idx "
                "ON clients_client (province, city) WHERE is_deleted = false;"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS clients_province_city_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS clients_blocklisted_active_idx "
                "ON clients_client (is_blocklisted) WHERE is_deleted = false;"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS clients_blocklisted_active_idx;"
            ),
        ),
    ]
