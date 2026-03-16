# Generated manually on 2026-03-10
# Fix labor_warranty_months column - make it nullable

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('installations', '0020_airconunit_compressor_warranty_months'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'installations_airconunit'
                    AND column_name = 'labor_warranty_months'
                ) THEN
                    ALTER TABLE installations_airconunit
                        ALTER COLUMN labor_warranty_months DROP NOT NULL;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
