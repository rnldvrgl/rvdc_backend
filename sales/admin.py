from django.contrib import admin
from .models import SalesTransaction, SalesItem


class SalesItemInline(admin.TabularInline):
    model = SalesItem
    extra = 0
    readonly_fields = (
        "item",
        "quantity",
        "retail_price",
        "discount_amount",
        "final_price",
    )
    can_delete = False


@admin.register(SalesTransaction)
class SalesTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sales_clerk",
        "client",
        "total_payment",
        "voided",
        "created_at",
    )
    list_filter = ("voided", "created_at")
    search_fields = ("id", "sales_clerk__username", "client__name")
    inlines = [SalesItemInline]
    readonly_fields = (
        "sales_clerk",
        "client",
        "total_payment",
        "voided",
        "voided_at",
        "void_reason",
        "created_at",
    )
    ordering = ("-created_at",)


@admin.register(SalesItem)
class SalesItemAdmin(admin.ModelAdmin):
    list_display = ("transaction", "item", "quantity", "final_price")
    search_fields = ("transaction__id", "item__name")
    readonly_fields = (
        "transaction",
        "item",
        "quantity",
        "retail_price",
        "discount_amount",
        "final_price",
    )
