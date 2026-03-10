# Generated manually on 2026-03-10

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('installations', '0018_alter_airconmodel_horsepower'),
        ('quotations', '0003_add_notes_and_aircon_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotationitem',
            name='aircon_unit',
            field=models.ForeignKey(
                blank=True,
                help_text='Optional link to a specific aircon unit from inventory',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='installations.airconunit'
            ),
        ),
    ]
