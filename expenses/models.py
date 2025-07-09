from django.db import models


class Expense(models.Model):
    stall = models.ForeignKey(
        "inventory.Stall", on_delete=models.CASCADE, related_name="expenses"
    )
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "users.CustomUser", on_delete=models.SET_NULL, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)
    source = models.CharField(
        max_length=20,
        choices=[("manual", "Manual"), ("transfer", "Transfer")],
        default="manual",
    )
    transfer = models.ForeignKey(
        "inventory.StockTransfer", on_delete=models.CASCADE, null=True, blank=True
    )

    def save(self, *args, **kwargs):
        if self.source == "transfer" and not self.transfer:
            raise ValueError("Transfer must be set for transfer expenses.")
        super().save(*args, **kwargs)


class ExpenseItem(models.Model):
    expense = models.ForeignKey(
        "expenses.Expense", on_delete=models.CASCADE, related_name="items"
    )
    item = models.ForeignKey("inventory.Item", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        if not self.total_price:
            self.total_price = self.quantity * self.item.retail_price
        if self.expense.paid_amount > 0:
            raise ValueError("Cannot edit items after payments have been made.")
        super().save(*args, **kwargs)
