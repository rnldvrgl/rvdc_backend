from django.utils.timezone import now
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from rest_framework.exceptions import NotFound
from inventory.models import Stock
from sales.models import SalesTransaction


def void_sales_transaction(transaction_id: int, user, reason: str):
    try:
        txn = (
            SalesTransaction.objects.select_related("stall")
            .prefetch_related("items__item")
            .get(pk=transaction_id)
        )
    except SalesTransaction.DoesNotExist:
        raise NotFound("Transaction not found.")

    if txn.voided:
        raise ValidationError("Transaction is already voided.")

    if not txn.stall:
        raise ValidationError("Transaction does not have a stall assigned.")

    with db_transaction.atomic():
        # Restock items with row-level lock
        for sale_item in txn.items.all():
            item = sale_item.item
            if not item:
                continue
            qty = sale_item.quantity
            stock, _ = Stock.objects.select_for_update().get_or_create(
                stall=txn.stall, item=item, defaults={"quantity": 0}
            )
            stock.quantity += qty
            stock.save(update_fields=["quantity", "updated_at"])

        # Mark transaction as void
        txn.voided = True
        txn.voided_at = now()
        txn.void_reason = reason
        txn.save(update_fields=["voided", "voided_at", "void_reason"])
        txn.update_payment_status()

    return txn


def unvoid_sales_transaction(transaction_id: int, user):
    try:
        txn = (
            SalesTransaction.objects.select_related("stall")
            .prefetch_related("items__item")
            .get(pk=transaction_id)
        )
    except SalesTransaction.DoesNotExist:
        raise NotFound("Transaction not found.")

    if not txn.voided:
        raise ValidationError("Transaction is not voided.")

    if not txn.stall:
        raise ValidationError("Transaction does not have a stall assigned.")

    with db_transaction.atomic():
        # Check stock availability with row-level lock before deducting
        for sale_item in txn.items.all():
            item = sale_item.item
            if not item:
                continue
            qty = sale_item.quantity
            stock = Stock.objects.select_for_update().filter(
                stall=txn.stall, item=item
            ).first()
            if not stock or stock.quantity < qty:
                raise ValidationError(
                    f"Cannot unvoid. Not enough stock of {item.name} in {txn.stall.name}. "
                    f"Available: {stock.quantity if stock else 0}, Needed: {qty}"
                )

        # Deduct items again
        for sale_item in txn.items.all():
            item = sale_item.item
            if not item:
                continue
            qty = sale_item.quantity
            stock = Stock.objects.select_for_update().get(
                stall=txn.stall, item=item
            )
            stock.quantity -= qty
            stock.save(update_fields=["quantity", "updated_at"])

        txn.voided = False
        txn.voided_at = None
        txn.void_reason = ""
        txn.save(update_fields=["voided", "voided_at", "void_reason"])
        txn.update_payment_status()

    return txn
