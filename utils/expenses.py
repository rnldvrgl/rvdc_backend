from expenses.models import Expense, ExpenseItem


def create_expense_from_transfer(stall, transfer_items, created_by):
    total = sum(item.quantity * item.item.cost for item in transfer_items)
    expense = Expense.objects.create(
        stall=stall,
        total_price=total,
        description="Credited stock transfer",
        created_by=created_by,
        source="transfer",
    )

    for item in transfer_items:
        ExpenseItem.objects.create(
            expense=expense,
            item=item.item,
            quantity=item.quantity,
            total_price=item.quantity * item.item.cost,
        )
