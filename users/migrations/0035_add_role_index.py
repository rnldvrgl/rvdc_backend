from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("users", "0034_alter_systemsettings_google_sheets_spreadsheet_id_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS users_role_active_idx "
                "ON users_customuser (role) WHERE is_deleted = false;"
            ),
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS users_role_active_idx;"
            ),
        ),
    ]
