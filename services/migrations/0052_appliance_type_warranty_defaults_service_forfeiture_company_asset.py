from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0051_add_back_job_and_custom_description"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- ApplianceType: warranty defaults ---
        migrations.AddField(
            model_name="appliancetype",
            name="default_labor_warranty_months",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Default labor warranty in months auto-applied to new service appliances of this type (0 = no default)",
            ),
        ),
        migrations.AddField(
            model_name="appliancetype",
            name="default_unit_warranty_months",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Default unit/parts warranty in months applied only for brand-new installation services (0 = no default)",
            ),
        ),
        # --- Service: completion + claim tracking ---
        migrations.AddField(
            model_name="service",
            name="completed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When the service status was set to completed",
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="claimed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When the client picked up the appliance or RVDC delivered it back (carry-in / pull-out)",
            ),
        ),
        # --- Service: forfeiture ---
        migrations.AddField(
            model_name="service",
            name="is_forfeited",
            field=models.BooleanField(
                default=False,
                help_text="Appliance declared as company property (unclaimed >2 mo or client sold)",
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="forfeited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="service",
            name="forfeiture_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("unclaimed", "Unclaimed \u2013 2-Month Policy"),
                    ("client_sold", "Client Sold to Company"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="forfeiture_notes",
            field=models.TextField(
                blank=True,
                help_text="Notes on forfeiture (condition, estimated value, decision rationale)",
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="acquisition_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Agreed price when client sells the appliance to the company",
                max_digits=10,
                null=True,
            ),
        ),
        # --- PaymentStatus: WRITTEN_OFF ---
        migrations.AlterField(
            model_name="service",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("unpaid", "Unpaid"),
                    ("partial", "Partial"),
                    ("paid", "Paid"),
                    ("refunded", "Refunded"),
                    ("n/a", "N/A (Complementary)"),
                    ("written_off", "Written Off (Forfeited)"),
                ],
                default="unpaid",
                max_length=30,
            ),
        ),
        # --- CompanyAsset model ---
        migrations.CreateModel(
            name="CompanyAsset",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "appliance_description",
                    models.CharField(
                        blank=True,
                        help_text="Brief description of the appliance (type, brand, model, serial)",
                        max_length=255,
                    ),
                ),
                (
                    "acquisition_type",
                    models.CharField(
                        choices=[
                            ("unclaimed", "Unclaimed \u2013 2-Month Policy"),
                            ("client_sold", "Client Sold to Company"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "acquisition_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Agreed price for client-sold acquisitions (null for unclaimed)",
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "acquired_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "condition_notes",
                    models.TextField(
                        blank=True,
                        help_text="Condition of the appliance at time of acquisition",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("holding", "In Holding"),
                            ("sold", "Sold"),
                            ("repurposed", "Repurposed / Used In-House"),
                            ("disposed", "Disposed / Scrapped"),
                        ],
                        default="holding",
                        max_length=20,
                    ),
                ),
                ("disposed_at", models.DateTimeField(blank=True, null=True)),
                ("disposal_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "acquired_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="declared_company_assets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        help_text="The service where the appliance originated",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="company_assets",
                        to="services.service",
                    ),
                ),
                (
                    "service_appliance",
                    models.ForeignKey(
                        blank=True,
                        help_text="Specific appliance record (if tracked per-appliance)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="company_asset_records",
                        to="services.serviceappliance",
                    ),
                ),
            ],
            options={
                "verbose_name": "Company Asset",
                "verbose_name_plural": "Company Assets",
                "ordering": ["-acquired_at"],
            },
        ),
    ]
