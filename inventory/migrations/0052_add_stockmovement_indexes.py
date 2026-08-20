from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("inventory", "0051_add_more_indexes"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS inventory_stockmovement_created_at_idx "
                "ON inventory_stockmovement (created_at);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS inventory_stockmovement_created_at_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS inventory_stockmovement_item_stall_idx "
                "ON inventory_stockmovement (item_id, stall_id);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS inventory_stockmovement_item_stall_idx;"
            ),
        ),
    ]
