from django.contrib import admin
from .models import RemittanceRecord, CashDenominationBreakdown


@admin.register(RemittanceRecord)
class RemittanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "stall",
        "created_at",
        "total_sales_cash",
        "total_expenses",
        "expected_remittance",
        "declared_amount",
        "remitted_amount",
        "is_remitted",
    )
    list_filter = ("stall", "is_remitted", "created_at")
    search_fields = ("stall__name", "notes")
    readonly_fields = (
        "expected_remittance",
        "total_collected",
        "balance",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def expected_remittance(self, obj):
        return obj.expected_remittance

    def total_collected(self, obj):
        return obj.total_collected

    def balance(self, obj):
        return obj.balance

    expected_remittance.short_description = "Expected"
    total_collected.short_description = "Collected Total"
    balance.short_description = "Balance"


@admin.register(CashDenominationBreakdown)
class CashDenominationBreakdownAdmin(admin.ModelAdmin):
    list_display = (
        "remittance",
        "total_remitted_amount",
        "total_cash_declared",
        "cod_amount",
    )
    readonly_fields = (
        "total_remitted_amount",
        "total_cash_declared",
        "cod_amount",
        "cod_breakdown",
    )
    search_fields = ("remittance__stall__name",)
