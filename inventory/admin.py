from django.contrib import admin
from inventory.models import Item, Stall, Stock, StockTransfer, StockTransferItem

# Register your models here.
admin.site.register(Item)
admin.site.register(Stall)
admin.site.register(Stock)
admin.site.register(StockTransfer)


@admin.register(StockTransferItem)
class StockTransferItemAdmin(admin.ModelAdmin):
    list_display = ("transfer", "item", "quantity")
    list_filter = ("transfer", "item")
    search_fields = ("transfer__id", "item__name")
    ordering = ("transfer__transfer_date",)
    raw_id_fields = ("transfer", "item")
    readonly_fields = ("transfer", "item", "quantity")

    def has_delete_permission(self, request, obj=None):
        return False
