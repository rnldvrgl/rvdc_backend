from django.contrib import admin
from .models import ServiceRequest, ServiceStep, ServiceRequestItem


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client",
        "appliance_type",
        "brand",
        "unit_type",
        "service_type",
        "status",
        "technician",
        "date_received",
        "date_completed",
    )
    list_filter = ("appliance_type", "service_type", "status", "technician")
    search_fields = ("client__name", "brand", "unit_type")
    readonly_fields = ("date_received",)


@admin.register(ServiceStep)
class ServiceStepAdmin(admin.ModelAdmin):
    list_display = ("service_request", "service_type", "performed_on")
    list_filter = ("service_type",)
    search_fields = ("service_request__client__name",)


@admin.register(ServiceRequestItem)
class ServiceRequestItemAdmin(admin.ModelAdmin):
    list_display = (
        "service_request",
        "item",
        "quantity_used",
        "deducted_from_stall",
        "deducted_by",
        "deducted_at",
    )
    list_filter = ("item", "deducted_from_stall")
    search_fields = ("item__name", "service_request__client__name")
