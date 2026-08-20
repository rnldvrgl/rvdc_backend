from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("services", "0063_alter_serviceextracharge_id_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS service_payment_status_created_idx "
                "ON services_service (payment_status, created_at);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS service_payment_status_created_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS services_payment_date_idx "
                "ON services_servicepayment (payment_date);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS services_payment_date_idx;"
            ),
        ),
    ]
