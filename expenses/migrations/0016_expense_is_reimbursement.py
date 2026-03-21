from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0015_alter_expense_paid_amount_alter_expense_total_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="is_reimbursement",
            field=models.BooleanField(
                default=False,
                help_text="If true, this is a reimbursement/credit that adds cash back to the stall instead of deducting it.",
            ),
        ),
    ]
