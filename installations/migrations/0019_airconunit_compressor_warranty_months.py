# Generated manually on 2026-03-10
# Fix compressor_warranty_months column - make it nullable

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('installations', '0018_alter_airconmodel_horsepower'),
    ]

    operations = [
        migrations.RunSQL(
            # Make the column nullable only if it already exists (e.g. existing DB)
            sql="""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'installations_airconunit'
                    AND column_name = 'compressor_warranty_months'
                ) THEN
                    ALTER TABLE installations_airconunit
                        ALTER COLUMN compressor_warranty_months DROP NOT NULL;
                END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
