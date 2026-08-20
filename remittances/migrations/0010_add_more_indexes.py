from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("remittances", "0009_remittancerecord_client_fund_deposits_cash_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS remittances_remittance_date_idx "
                "ON remittances_remittancerecord (remittance_date);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS remittances_remittance_date_idx;"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS remittances_stall_remittance_date_idx "
                "ON remittances_remittancerecord (stall_id, remittance_date);"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS remittances_stall_remittance_date_idx;"
            ),
        ),
    ]
