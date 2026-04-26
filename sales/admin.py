# sales/admin.py
from django.contrib import admin
from .models import SalesTransaction, SalesPayment, SalesItem, StallMonthlySheet


class SalesItemInline(admin.TabularInline):
    model = SalesItem
    extra = 0
    readonly_fields = ("line_total",)
    fields = ("item", "description", "quantity", "final_price_per_unit", "line_total")


class SalesPaymentInline(admin.TabularInline):
    model = SalesPayment
    extra = 0
    fields = ("payment_type", "amount", "payment_date")


@admin.register(SalesTransaction)
class SalesTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "stall",
        "client",
        "manual_receipt_number",
        "payment_status",
        "total_paid",
        "computed_total",
        "change_amount",
        "voided",
        "created_at",
    )
    list_filter = ("stall", "payment_status", "voided", "created_at")
    search_fields = ("manual_receipt_number", "client__name")
    inlines = [SalesItemInline, SalesPaymentInline]
    readonly_fields = (
        "system_receipt_number",
        "computed_total",
        "total_paid",
        "change_amount",
    )

    def computed_total(self, obj):
        return obj.computed_total

    def total_paid(self, obj):
        return obj.total_paid


@admin.register(SalesPayment)
class SalesPaymentAdmin(admin.ModelAdmin):
    list_display = ("transaction", "payment_type", "amount", "payment_date")
    list_filter = ("payment_type", "payment_date")
    search_fields = ("transaction__manual_receipt_number",)


@admin.register(SalesItem)
class SalesItemAdmin(admin.ModelAdmin):
    list_display = (
        "transaction",
        "item",
        "description",
        "quantity",
        "final_price_per_unit",
        "line_total",
    )
    search_fields = ("description", "item__name")
    list_filter = ("item",)

    def line_total(self, obj):
        return obj.line_total


@admin.register(StallMonthlySheet)
class StallMonthlySheetAdmin(admin.ModelAdmin):
    list_display = (
        "stall",
        "month_key",
        "is_active",
        "shared_ok",
        "shared_to_email",
        "shared_at",
        "updated_at",
    )
    list_filter = ("stall", "is_active", "shared_ok", "month_key")
    search_fields = ("stall__name", "month_key", "spreadsheet_id", "shared_to_email")
