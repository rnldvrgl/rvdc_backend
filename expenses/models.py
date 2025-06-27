from django.db import models
from inventory.models import Stall
from users.models import CustomUser
from inventory.models import Item


class Expense(models.Model):
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE, related_name="expenses")
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(
        max_length=20,
        choices=[("manual", "Manual"), ("transfer", "Transfer")],
        default="manual",
    )


class ExpenseItem(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
