from django.contrib import admin
from .models import Expense, ExpenseItem


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "stall",
        "total_price",
        "paid_amount",
        "is_closed",
        "source",
        "created_at",
    )
    search_fields = ("description",)


@admin.register(ExpenseItem)
class ExpenseItemAdmin(admin.ModelAdmin):
    list_display = ("expense", "item", "quantity", "total_price")
