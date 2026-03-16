from django.db import migrations


def seed_price_list_templates(apps, schema_editor):
    QuotationTermsTemplate = apps.get_model("quotations", "QuotationTermsTemplate")

    # Terms & Conditions for Price List
    QuotationTermsTemplate.objects.get_or_create(
        name="Price List - Terms & Conditions",
        category="terms_conditions",
        defaults={
            "lines": [
                "Prices are subject to change without prior notice.",
                "All prices are in Philippine Peso (PHP) and are inclusive of VAT.",
                "Warranty coverage varies per unit — please inquire for specific terms.",
                "Installation charges are not included in the listed prices unless otherwise stated.",
                "Delivery charges may apply depending on location and quantity.",
                "Product availability is subject to current stock levels.",
                "Images and specifications are for reference only and may vary from actual units.",
                "This price list is valid for 30 days from the date of issue.",
            ],
            "is_default": False,
            "is_active": True,
        },
    )

    # Payment Terms for Price List
    QuotationTermsTemplate.objects.get_or_create(
        name="Price List - Payment Terms",
        category="payment_terms",
        defaults={
            "lines": [
                "Full payment is required upon confirmation of order.",
                "We accept Cash, GCash, and Bank Transfer payments.",
                "For bulk orders, a 50% downpayment is required upon order placement; remaining balance due before delivery.",
                "Cheque payments are subject to clearing before release of units.",
                "Official receipts will be issued upon full payment.",
                "No refunds on confirmed orders; exchange may be arranged within 7 days subject to inspection.",
            ],
            "is_default": False,
            "is_active": True,
        },
    )


def reverse(apps, schema_editor):
    QuotationTermsTemplate = apps.get_model("quotations", "QuotationTermsTemplate")
    QuotationTermsTemplate.objects.filter(
        name__in=[
            "Price List - Terms & Conditions",
            "Price List - Payment Terms",
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("quotations", "0007_add_quotation_type_and_promo_price"),
    ]

    operations = [
        migrations.RunPython(seed_price_list_templates, reverse),
    ]
