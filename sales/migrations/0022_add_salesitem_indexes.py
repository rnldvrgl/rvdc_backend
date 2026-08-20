from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("sales", "0021_add_indexes"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS salesitem_item_idx "
                "ON sales_salesitem (item_id);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS salesitem_item_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS salesitem_transaction_item_idx "
                "ON sales_salesitem (transaction_id, item_id);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS salesitem_transaction_item_idx;"
            ),
        ),
    ]
