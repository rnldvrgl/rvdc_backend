"""
Add document_type and with_2307 fields to SalesTransaction.

- document_type: 'or' (Official Receipt) for Main Stall, 'si' (Sales Invoice) for Sub Stall
- with_2307: boolean flag for BIR Form 2307 applicability (only valid for OR)
- DB constraint: SI transactions cannot have with_2307=True
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0015_add_transaction_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="salestransaction",
            name="document_type",
            field=models.CharField(
                choices=[("or", "Official Receipt"), ("si", "Sales Invoice")],
                default="si",
                help_text="OR for Main Stall, SI for Sub Stall.",
                max_length=2,
            ),
        ),
        migrations.AddField(
            model_name="salestransaction",
            name="with_2307",
            field=models.BooleanField(
                default=False,
                help_text="Whether this transaction has an associated BIR Form 2307. Only valid for OR (Main Stall).",
            ),
        ),
        migrations.AddIndex(
            model_name="salestransaction",
            index=models.Index(
                fields=["document_type"], name="sales_doc_type_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="salestransaction",
            index=models.Index(
                fields=["document_type", "with_2307"],
                name="sales_doc_type_2307_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="salestransaction",
            constraint=models.CheckConstraint(
                check=~models.Q(document_type="si", with_2307=True),
                name="si_cannot_have_2307",
            ),
        ),
    ]
