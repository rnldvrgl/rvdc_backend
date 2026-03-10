from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quotations", "0005_quotationpayment"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotationpayment",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("cash", "Cash"),
                    ("gcash", "GCash"),
                    ("bank_transfer", "Bank Transfer"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="quotationpayment",
            name="reference_number",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="quotationpayment",
            name="si_number",
            field=models.CharField(
                blank=True,
                help_text="Sales Invoice / Receipt number",
                max_length=100,
            ),
        ),
        migrations.RemoveField(
            model_name="quotationpayment",
            name="receipt_number",
        ),
    ]
