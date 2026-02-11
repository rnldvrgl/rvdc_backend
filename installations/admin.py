from django.contrib import admin

from installations.models import (
    AirconBrand,
    AirconModel,
    AirconUnit,
    WarrantyClaim,
)


@admin.register(AirconBrand)
class AirconBrandAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "created_at"]
    search_fields = ["name"]
    ordering = ["name"]


@admin.register(AirconModel)
class AirconModelAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "brand",
        "name",
        "horsepower",
        "retail_price",
        "promo_price",
        "aircon_type",
        "is_inverter",
        "discount_percentage",
        "has_discount",
    ]
    list_filter = ["brand", "aircon_type", "horsepower", "is_inverter"]
    search_fields = ["name", "brand__name"]
    ordering = ["brand__name", "name"]


@admin.register(AirconUnit)
class AirconUnitAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "serial_number",
        "model",
        "stall",
        "is_sold",
        "is_reserved",
        "warranty_status",
        "warranty_days_left",
        "free_cleaning_redeemed",
    ]
    list_filter = [
        "is_sold",
        "free_cleaning_redeemed",
        "stall",
        "model__brand",
    ]
    search_fields = ["serial_number", "model__name", "model__brand__name"]
    readonly_fields = [
        "warranty_end_date",
        "warranty_status",
        "warranty_days_left",
        "is_reserved",
        "is_available_for_sale",
        "sale_price",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    fieldsets = (
        ("Basic Information", {
            "fields": ("model", "serial_number", "stall")
        }),
        ("Sale Information", {
            "fields": ("sale", "installation_service", "is_sold", "reserved_by", "reserved_at")
        }),
        ("Warranty Information", {
            "fields": (
                "warranty_start_date",
                "warranty_period_months",
                "warranty_end_date",
                "warranty_status",
                "warranty_days_left",
                "free_cleaning_redeemed",
            )
        }),
        ("Computed Fields", {
            "fields": ("is_reserved", "is_available_for_sale", "sale_price")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(WarrantyClaim)
class WarrantyClaimAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "unit",
        "claim_type",
        "status",
        "claim_date",
        "is_valid_claim",
        "reviewed_by",
        "service",
    ]
    list_filter = [
        "status",
        "claim_type",
        "is_valid_claim",
        "claim_date",
        "reviewed_at",
    ]
    search_fields = [
        "unit__serial_number",
        "unit__model__name",
        "unit__sale__client__name",
        "issue_description",
    ]
    readonly_fields = [
        "is_pending",
        "is_approved",
        "warranty_days_remaining_at_claim",
    ]
    ordering = ["-claim_date"]

    fieldsets = (
        ("Claim Information", {
            "fields": ("unit", "claim_type", "status", "service")
        }),
        ("Issue Details", {
            "fields": ("issue_description", "customer_notes")
        }),
        ("Assessment", {
            "fields": (
                "technician_assessment",
                "is_valid_claim",
                "estimated_cost",
                "actual_cost",
            )
        }),
        ("Review Information", {
            "fields": (
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
            )
        }),
        ("Dates", {
            "fields": (
                "claim_date",
                "completed_at",
            )
        }),
        ("Computed Fields", {
            "fields": (
                "is_pending",
                "is_approved",
                "warranty_days_remaining_at_claim",
            ),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def save_model(self, request, obj, form, change):
        """Automatically set reviewed_by when approving/rejecting."""
        if not change:
            # New claim - no need to set reviewed_by
            pass
        else:
            # Check if status changed to approved or rejected
            if obj.status in ['approved', 'rejected'] and not obj.reviewed_by:
                obj.reviewed_by = request.user

        super().save_model(request, obj, form, change)
