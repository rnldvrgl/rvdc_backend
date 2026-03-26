from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("services", "0041_add_transaction_date_total_service_fee_auto_adjust_labor"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="discount_applied_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who applied the discount",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="discounts_applied",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="discount_applied_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the discount was applied",
                null=True,
            ),
        ),
    ]
