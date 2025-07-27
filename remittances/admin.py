# from django.contrib import admin
# from .models import RemittanceRecord, CashDenominationBreakdown


# @admin.register(RemittanceRecord)
# class RemittanceRecordAdmin(admin.ModelAdmin):
#     list_display = (
#         "stall",
#         "created_at",
#         "is_remitted",
#         "remitted_amount",
#         "total_collected",
#         "expected_remittance",
#         "balance",
#     )
#     list_filter = ("stall", "is_remitted", "coins_remitted")
#     search_fields = ("stall__name", "remitted_by__username")
#     readonly_fields = (
#         "expected_remittance",
#         "total_collected",
#         "balance",
#         "updated_at",
#     )
#     date_hierarchy = "created_at"

#     def total_collected(self, obj):
#         return obj.total_collected

#     def expected_remittance(self, obj):
#         return obj.expected_remittance

#     def balance(self, obj):
#         return obj.balance


# @admin.register(CashDenominationBreakdown)
# class CashDenominationBreakdownAdmin(admin.ModelAdmin):
#     list_display = (
#         "remittance",
#         "total_remitted_amount",
#         "cod_amount",
#         "total_cash_declared",
#     )
#     search_fields = ("remittance__stall__name",)
#     readonly_fields = ("total_remitted_amount", "cod_amount", "total_cash_declared")
