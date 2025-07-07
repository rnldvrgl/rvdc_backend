from django.db import models
from users.models import CustomUser
from inventory.models import Item
from clients.models import Client
from inventory.models import Stall


class SalesTransaction(models.Model):
    sales_clerk = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True)
    total_payment = models.DecimalField(max_digits=10, decimal_places=2)
    voided = models.BooleanField(default=False)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True, null=True)
    receipt_number = models.CharField(
        max_length=100, unique=True, blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Sale #{self.id} - OR {self.receipt_number or 'N/A'}"


class SalesItem(models.Model):
    transaction = models.ForeignKey(
        SalesTransaction, related_name="items", on_delete=models.CASCADE
    )
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    final_price = models.DecimalField(max_digits=10, decimal_places=2)
