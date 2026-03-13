from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('installations', '0025_airconmodel_compressor_warranty_months'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='airconbrand',
            options={
                'ordering': ['name'],
                'verbose_name': 'Aircon Brand',
                'verbose_name_plural': 'Aircon Brands',
            },
        ),
        migrations.AlterModelOptions(
            name='airconmodel',
            options={
                'ordering': ['brand__name', 'name'],
                'verbose_name': 'Aircon Model',
                'verbose_name_plural': 'Aircon Models',
            },
        ),
    ]
