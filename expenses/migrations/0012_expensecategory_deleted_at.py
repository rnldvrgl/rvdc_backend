# Generated migration - Add deleted_at to ExpenseCategory for soft-delete support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0011_remove_recurring_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="expensecategory",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
