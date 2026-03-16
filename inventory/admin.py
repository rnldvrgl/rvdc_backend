from django.contrib import admin

from inventory.models import (
    CustomItemTemplate,
    Item,
    Stall,
    Stock,
    StockRequest,
    StockRoomStock,
)


@admin.register(Stall)
class StallAdmin(admin.ModelAdmin):
    """
    Read-only admin for stalls. Stalls are system-managed (Main/Sub) and
    should not be created, edited, or deleted via the admin UI.
    """

    list_display = (
        "name",
        "location",
        "inventory_enabled",
        "is_system",
        "is_deleted",
        "created_at",
        "updated_at",
    )
    list_filter = ("inventory_enabled", "is_system", "is_deleted")
    search_fields = ("name", "location")
    ordering = ("name",)
    readonly_fields = (
        "name",
        "location",
        "inventory_enabled",
        "is_system",
        "is_deleted",
        "created_at",
        "updated_at",
    )

    # Disallow add/change/delete, but allow viewing records
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "category",
        "unit_of_measure",
        "retail_price",
        "is_deleted",
    )
    list_filter = ("category", "unit_of_measure", "is_deleted")
    search_fields = ("name", "sku", "category__name")
    ordering = ("name",)
    raw_id_fields = ("category",)


@admin.register(StockRoomStock)
class StockRoomStockAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "quantity",
        "low_stock_threshold",
        "is_deleted",
        "updated_at",
    )
    list_filter = ("is_deleted",)
    search_fields = ("item__name",)
    ordering = ("item__name",)
    raw_id_fields = ("item",)


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        "stall",
        "item",
        "quantity",
        "reserved_quantity",
        "low_stock_threshold",
        "track_stock",
        "is_deleted",
        "updated_at",
    )
    list_filter = ("stall", "item", "track_stock", "is_deleted")
    search_fields = ("stall__name", "item__name")
    ordering = ("stall__name", "item__name")
    raw_id_fields = ("stall", "item")


@admin.register(StockRequest)
class StockRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "item",
        "stall",
        "requested_quantity",
        "status",
        "source",
        "requested_by",
        "approved_by",
        "created_at",
    )
    list_filter = ("status", "source")
    search_fields = ("item__name", "notes")
    ordering = ("-created_at",)
    raw_id_fields = ("item", "stall", "service", "appliance_item", "service_item", "requested_by", "approved_by")


@admin.register(CustomItemTemplate)
class CustomItemTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "default_price", "is_active", "created_by", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)
    raw_id_fields = ("created_by",)
