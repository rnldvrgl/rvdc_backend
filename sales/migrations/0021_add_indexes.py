from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("sales", "0020_stallmonthlysheet"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS sales_active_created_at_idx "
                "ON sales_salestransaction (created_at) "
                "WHERE is_deleted = false AND voided = false;"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS sales_active_created_at_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS sales_payment_date_idx "
                "ON sales_salespayment (payment_date);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS sales_payment_date_idx;"
            ),
        ),
    ]
