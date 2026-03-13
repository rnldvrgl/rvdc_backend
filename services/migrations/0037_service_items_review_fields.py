import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0036_simplify_appliance_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="service_parts_needed_notes",
            field=models.TextField(
                blank=True,
                help_text="Manager/technician notes on what service-level parts are needed (for clerk reference)",
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="service_items_checked",
            field=models.BooleanField(
                default=False,
                help_text="Whether service-level items/parts have been reviewed and confirmed by clerk",
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="service_items_checked_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who confirmed the service-level items",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="service_items_checked_services",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="service_items_checked_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When service-level items were confirmed",
                null=True,
            ),
        ),
    ]
