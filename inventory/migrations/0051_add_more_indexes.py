from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("inventory", "0050_alter_directstockrequestbatch_notes"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS inventory_items_created_at_active_idx "
                "ON inventory_item (created_at) WHERE is_deleted = false;"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS inventory_items_created_at_active_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS inventory_items_is_tracked_active_idx "
                "ON inventory_item (is_tracked) WHERE is_deleted = false;"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS inventory_items_is_tracked_active_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS inventory_stock_item_isdeleted_tracked_idx "
                "ON inventory_stock (item_id, is_deleted) WHERE track_stock = true;"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS inventory_stock_item_isdeleted_tracked_idx;"
            ),
        ),
    ]
