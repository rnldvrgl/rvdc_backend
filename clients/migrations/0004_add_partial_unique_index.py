from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            "clients",
            "0003_rename_phone_client_contact_number",
        ),  # change to your latest migration
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE UNIQUE INDEX unique_active_client
                ON clients_client (full_name, contact_number)
                WHERE is_deleted = FALSE;
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS unique_active_client;
            """,
        )
    ]
