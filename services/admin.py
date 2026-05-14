from django.contrib import admin

from .models import (
    ApplianceItemUsed,
    ApplianceType,
    JobOrderTemplatePrint,
    Service,
    ServiceAppliance,
    ServicePartTemplate,
    ServicePartTemplateLine,
    ServiceExtraCharge,
    ServicePayment,
    TechnicianAssignment,
)
from django.contrib import messages

from .business_logic import ServicePaymentManager, RevenueCalculator


@admin.register(ServiceExtraCharge)
class ServiceExtraChargeAdmin(admin.ModelAdmin):
    list_display = ("id", "service", "description", "amount", "created_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("description", "service__id")
    raw_id_fields = ("service", "created_by")


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
    actions = [
        'admin_sync_sub_sales_items',
        'admin_recalculate_revenue',
    ]

    def admin_sync_sub_sales_items(self, request, queryset):
        """Admin action: ensure each selected service has up-to-date sub stall sales items."""
        fixed = 0
        errors = 0
        for svc in queryset.select_related('related_sub_transaction'):
            try:
                ServicePaymentManager.sync_sub_sales_items(svc)
                fixed += 1
            except Exception as exc:  # pragma: no cover - admin safety
                errors += 1
                self.message_user(request, f"Service #{svc.id} error: {exc}", level=messages.ERROR)

        if fixed:
            self.message_user(request, f"Synced sub sales items for {fixed} service(s).", level=messages.SUCCESS)
        if errors:
            self.message_user(request, f"Encountered errors for {errors} service(s). See details above.", level=messages.WARNING)

    admin_sync_sub_sales_items.short_description = "Sync sub-stall sales items (fix missing parts transactions)"

    def admin_recalculate_revenue(self, request, queryset):
        """Admin action: recalculate revenue for selected services."""
        for svc in queryset:
            try:
                RevenueCalculator.calculate_service_revenue(svc, save=True)
            except Exception as exc:  # pragma: no cover
                self.message_user(request, f"Service #{svc.id} revenue error: {exc}", level=messages.ERROR)

        self.message_user(request, f"Recalculation triggered for {queryset.count()} service(s).", level=messages.SUCCESS)

    admin_recalculate_revenue.short_description = "Recalculate service revenue"


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


class ServicePartTemplateLineInline(admin.TabularInline):
    model = ServicePartTemplateLine
    extra = 1


@admin.register(ServicePartTemplate)
class ServicePartTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_by", "updated_at")
    search_fields = ("name", "description", "lines__item__name", "lines__custom_description")
    list_filter = ("created_at", "updated_at")
    ordering = ("name",)
    inlines = [ServicePartTemplateLineInline]
    list_select_related = ("created_by",)
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
