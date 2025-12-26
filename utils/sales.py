from django.utils.timezone import now
from django.core.exceptions import ValidationError
from rest_framework.exceptions import NotFound
from inventory.models import Stock
from sales.models import SalesTransaction


def void_sales_transaction(transaction_id: int, user, reason: str):
    try:
        transaction = (
            SalesTransaction.objects.select_related("stall")
            .prefetch_related("items__item")
            .get(pk=transaction_id)
        )
    except SalesTransaction.DoesNotExist:
        raise NotFound("Transaction not found.")

    if transaction.voided:
        raise ValidationError("Transaction is already voided.")

    if not transaction.stall:
        raise ValidationError("Transaction does not have a stall assigned.")

    # Restock items
    for sale_item in transaction.items.all():
        item = sale_item.item
        qty = sale_item.quantity
        stock, _ = Stock.objects.get_or_create(
            stall=transaction.stall, item=item, defaults={"quantity": 0}
        )
        stock.quantity += qty
        stock.save()

    # Mark transaction as void
    transaction.voided = True
    transaction.voided_at = now()
    transaction.void_reason = reason
    transaction.save()

    return transaction


def unvoid_sales_transaction(transaction_id: int, user):
    try:
        transaction = (
            SalesTransaction.objects.select_related("stall")
            .prefetch_related("items__item")
            .get(pk=transaction_id)
        )
    except SalesTransaction.DoesNotExist:
        raise NotFound("Transaction not found.")

    if not transaction.voided:
        raise ValidationError("Transaction is not voided.")

    if not transaction.stall:
        raise ValidationError("Transaction does not have a stall assigned.")

    # Check stock availability before deducting
    for sale_item in transaction.items.all():
        item = sale_item.item
        qty = sale_item.quantity
        stock = Stock.objects.filter(stall=transaction.stall, item=item).first()
        if not stock or stock.quantity < qty:
            raise ValidationError(
                f"Cannot unvoid. Not enough stock of {item.name} in {transaction.stall.name}. "
                f"Available: {stock.quantity if stock else 0}, Needed: {qty}"
            )

    # Deduct items again
    for sale_item in transaction.items.all():
        item = sale_item.item
        qty = sale_item.quantity
        stock = Stock.objects.get(stall=transaction.stall, item=item)
        stock.quantity -= qty
        stock.save()

    transaction.voided = False
    transaction.voided_at = None
    transaction.void_reason = ""
    transaction.save()

    return transaction
