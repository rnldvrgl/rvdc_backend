from django.utils.timezone import now
from django.core.exceptions import ValidationError
from rest_framework.exceptions import NotFound

from sales.models import SalesTransaction
from utils.logger import log_activity
from utils.inventory import deduct_inventory


def void_sales_transaction(transaction_id: int, user, reason: str):
    try:
        transaction = (
            SalesTransaction.objects.select_related("stall", "sales_clerk", "client")
            .prefetch_related("items")
            .get(pk=transaction_id)
        )
    except SalesTransaction.DoesNotExist:
        raise NotFound("Transaction not found.")

    if transaction.voided:
        raise ValidationError("Transaction is already voided.")

    transaction.voided = True
    transaction.voided_at = now()
    transaction.void_reason = reason
    transaction.save()

    log_activity(
        user=user,
        instance=transaction,  # ✅ Pass the instance
        action=f"Voided Sale #{transaction.id}",
        note=f"Reason: {reason}",
    )

    return transaction


def unvoid_sales_transaction(transaction_id: int, user):
    try:
        transaction = (
            SalesTransaction.objects.select_related("stall")
            .prefetch_related("items")
            .get(pk=transaction_id)
        )
    except SalesTransaction.DoesNotExist:
        raise NotFound("Transaction not found.")

    if not transaction.voided:
        raise ValidationError("Transaction is not voided.")

    if not transaction.stall:
        raise ValidationError("Stall information is missing from transaction.")

    inventory_data = [
        {"item": item.item, "quantity": item.quantity}
        for item in transaction.items.all()
    ]

    deduct_inventory(inventory_data, transaction.stall)

    transaction.voided = False
    transaction.voided_at = None
    transaction.void_reason = ""
    transaction.save()

    log_activity(
        user=user,
        instance=transaction,  # ✅ Pass the instance
        action=f"Undo Void Sale #{transaction.id}",
        note="Reinstated transaction",
    )

    return transaction
