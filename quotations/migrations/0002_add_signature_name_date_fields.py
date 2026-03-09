from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quotations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="authorized_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="quotation",
            name="authorized_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="quotation",
            name="client_acceptance_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="quotation",
            name="client_acceptance_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
