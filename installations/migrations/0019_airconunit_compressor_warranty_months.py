# Generated manually on 2026-03-10
# Fix compressor_warranty_months column - make it nullable

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('installations', '0018_alter_airconmodel_horsepower'),
    ]

    operations = [
        migrations.RunSQL(
            # Make the column nullable if it exists
            sql="ALTER TABLE installations_airconunit ALTER COLUMN compressor_warranty_months DROP NOT NULL;",
            reverse_sql="ALTER TABLE installations_airconunit ALTER COLUMN compressor_warranty_months SET NOT NULL;",
        ),
    ]
