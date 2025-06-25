from django.core.exceptions import ValidationError
from inventory.models import Stock


def deduct_inventory(items, stall):
    for entry in items:
        item = entry["item"]
        quantity = entry["quantity"]

        try:
            stock = Stock.objects.get(item=item, stall=stall, is_deleted=False)
        except Stock.DoesNotExist:
            raise ValidationError(
                f"Stock for item '{item.name}' not found in this stall."
            )

        if stock.quantity < quantity:
            raise ValidationError(f"Insufficient stock for item: {item.name}")

        stock.quantity -= quantity
        stock.save()
