from django.contrib import admin

from .models import (
    ApplianceItemUsed,
    ApplianceType,
    JobOrderTemplatePrint,
    Service,
    ServiceAppliance,
    ServicePayment,
    TechnicianAssignment,
)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client",
        "stall",
        "service_type",
        "service_mode",
        "pickup_date",
        "delivery_date",
        "status",
        "payment_status",
        "total_revenue",
        "total_paid",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "service_type",
        "service_mode",
        "status",
        "payment_status",
        "stall",
        "pickup_date",
        "created_at",
    )
    search_fields = (
        "client__full_name",
        "stall__name",
        "description",
        "override_address",
        "override_contact_person",
        "override_contact_number",
        "remarks",
        "notes",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("client", "stall")
    list_per_page = 25


@admin.register(ServiceAppliance)
class ServiceApplianceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "service",
        "appliance_type",
        "brand",
        "model",
        "serial_number",
        "status",
        "labor_fee",
        "labor_is_free",
    )
    list_filter = ("appliance_type", "status", "labor_is_free")
    search_fields = ("brand", "model", "serial_number", "service__client__full_name")
    ordering = ("appliance_type__name", "brand")
    list_select_related = ("service", "appliance_type")
    list_per_page = 25


@admin.register(ApplianceItemUsed)
class ApplianceItemUsedAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "appliance",
        "item",
        "quantity",
        "stall_stock",
        "is_free",
        "expense",
    )
    list_filter = ("is_free", "item")
    search_fields = ("appliance__service__client__full_name", "item__name")
    ordering = ("-id",)
    list_select_related = ("appliance", "item", "stall_stock", "expense")
    list_per_page = 25


@admin.register(TechnicianAssignment)
class TechnicianAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "service",
        "appliance",
        "technician",
        "assignment_type",
        "note",
    )
    list_filter = ("assignment_type",)
    search_fields = ("technician__username", "technician__first_name", "technician__last_name", "service__client__full_name")
    ordering = ("-id",)
    list_select_related = ("service", "appliance", "technician")
    list_per_page = 25


@admin.register(ApplianceType)
class ApplianceTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)
    ordering = ("name",)
    list_per_page = 25


@admin.register(JobOrderTemplatePrint)
class JobOrderTemplatePrintAdmin(admin.ModelAdmin):
    list_display = ("id", "start_number", "end_number", "printed_by", "printed_at")
    list_filter = ("printed_at",)
    search_fields = ("printed_by__username", "printed_by__first_name", "printed_by__last_name")
    ordering = ("-printed_at",)
    list_select_related = ("printed_by",)
    list_per_page = 25





@admin.register(ServicePayment)
class ServicePaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "service",
        "payment_type",
        "amount",
        "payment_date",
        "received_by",
        "created_at",
    )
    list_filter = ("payment_type", "payment_date", "created_at")
    search_fields = (
        "service__client__full_name",
        "received_by__username",
        "received_by__first_name",
        "received_by__last_name",
        "notes",
    )
    date_hierarchy = "payment_date"
    ordering = ("-payment_date",)
    list_select_related = ("service", "received_by")
    list_per_page = 25
    readonly_fields = ("created_at", "updated_at")
