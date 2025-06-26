from django.contrib import admin
from django import forms
from users.models import CustomUser
from .models import ServiceRequest, ServiceStep, ServiceRequestItem


# ✅ Inline for used items
class ServiceRequestItemInline(admin.TabularInline):
    model = ServiceRequestItem
    extra = 1


# ✅ Custom form to show technician names instead of IDs
class ServiceRequestForm(forms.ModelForm):
    technicians = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.all(),
        widget=forms.SelectMultiple,
        label="Technicians",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["technicians"].label_from_instance = (
            lambda obj: obj.get_full_name() or obj.username
        )

    class Meta:
        model = ServiceRequest
        fields = "__all__"


# ✅ Admin class for ServiceRequest
@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    form = ServiceRequestForm  # use custom form
    inlines = [ServiceRequestItemInline]

    list_display = (
        "id",
        "client",
        "appliance_type",
        "brand",
        "unit_type",
        "service_type",
        "status",
        "get_technicians",
        "date_received",
        "date_completed",
    )
    list_filter = ("appliance_type", "service_type", "status", "technicians")
    search_fields = ("client__name", "brand", "unit_type")
    readonly_fields = ("date_received",)

    def get_technicians(self, obj):
        return ", ".join(
            [t.get_full_name() or t.username for t in obj.technicians.all()]
        )

    get_technicians.short_description = "Technicians"


# ✅ Admin for ServiceStep
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
