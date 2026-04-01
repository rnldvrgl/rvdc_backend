from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0010_make_province_city_optional"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE clients_client DROP COLUMN IF EXISTS is_favorite;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
