# expenses/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from inventory.models import StockTransfer
from expenses.models import Expense, ExpenseItem
from users.models import CustomUser
from notifications.models import Notification


@receiver(post_save, sender=StockTransfer)
def create_expense_for_transfer(sender, instance, created, **kwargs):
    if created:
        expense = Expense.objects.create(
            stall=instance.to_stall,
            description=f"Expense for transfer {instance.id}",
            source="transfer",
            transfer=instance,
        )
        for detail in instance.details.all():
            ExpenseItem.objects.create(
                expense=expense,
                item=detail.item,
                quantity=detail.quantity,
                total_price=detail.quantity * detail.item.retail_price,
            )
        expense.save()

        # notify users in the receiving stall
        users = CustomUser.objects.filter(stall=instance.to_stall)
        for user in users:
            Notification.objects.create(
                user=user, message=f"New expense created from transfer #{instance.id}"
            )
