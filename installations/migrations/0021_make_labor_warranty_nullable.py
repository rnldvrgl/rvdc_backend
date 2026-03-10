# Generated manually on 2026-03-10
# Fix labor_warranty_months column - make it nullable

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('installations', '0020_airconunit_compressor_warranty_months'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE installations_airconunit ALTER COLUMN labor_warranty_months DROP NOT NULL;",
            reverse_sql="ALTER TABLE installations_airconunit ALTER COLUMN labor_warranty_months SET NOT NULL;",
        ),
    ]
