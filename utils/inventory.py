from django.db import transaction
from inventory.models import Item, Stall, Stock
from rest_framework.exceptions import ValidationError


def user_can_manage_stall(user, stall):
    """
    Checks if a user has permission to manage a stall.
    """
    return user.role == "admin" or user.assigned_stall == stall


@transaction.atomic
def create_item_with_initial_stock(validated_data, user=None):
    from inventory.models import Item, Stall, Stock, StockRoomStock

    """
    Creates an Item, initializes StockRoomStock with initial quantity, and sets zero stock for all stalls.

    validated_data: dict with keys:
        - name, category, retail_price
        - initial_stock_quantity, low_stock_threshold
    """
    item = Item.objects.create(
        name=validated_data["name"],
        category=validated_data["category"],
        retail_price=validated_data["retail_price"],
        wholesale_price=validated_data.get("wholesale_price", 0),
        technician_price=validated_data.get("technician_price", 0),
        cost_price=validated_data.get("cost_price", 0),
        unit_of_measure=validated_data.get("unit_of_measure", "pcs"),
        description=validated_data.get("description"),
    )

    initial_stock_quantity = validated_data.get("initial_stock_quantity", 0)
    low_stock_threshold = validated_data.get("low_stock_threshold", 5)

    # Create StockRoomStock with initial quantity
    StockRoomStock.objects.create(
        item=item,
        quantity=initial_stock_quantity,
        low_stock_threshold=low_stock_threshold,
    )

    # Create zero Stock entries only for stalls that are inventory owners
    for stall in Stall.objects.filter(is_deleted=False, inventory_enabled=True):
        Stock.objects.create(
            item=item,
            stall=stall,
            quantity=0,
            low_stock_threshold=low_stock_threshold,
        )

    return item


@transaction.atomic
def create_stall_with_initial_stocks(validated_data):
    from inventory.models import Item, Stall, Stock

    """
    Creates a Stall and sets up zero stock for all existing items.

    validated_data: dict with keys:
        - name, location, low_stock_threshold
    """
    low_stock_threshold = validated_data.get("low_stock_threshold", 5)
    stall = Stall.objects.create(
        name=validated_data["name"],
        location=validated_data["location"],
        inventory_enabled=validated_data.get("inventory_enabled", False),
        is_system=validated_data.get("is_system", False),
    )

    # Only create Stock rows for this stall if it is an inventory owner
    if stall.inventory_enabled:
        for item in Item.objects.filter(is_deleted=False):
            Stock.objects.create(
                item=item,
                stall=stall,
                quantity=0,
                low_stock_threshold=low_stock_threshold,
            )

    return stall


@transaction.atomic
def reserve_stock(item, stall, quantity):
    stock = Stock.objects.select_for_update().get(item=item, stall=stall)
    if stock.available_quantity < quantity:
        raise ValidationError(
            f"Not enough available stock to reserve {quantity} of {item.name}."
        )
    stock.reserved_quantity += quantity
    stock.save(update_fields=["reserved_quantity"])
    return stock


@transaction.atomic
def unreserve_stock(item, stall, quantity):
    stock = Stock.objects.select_for_update().get(item=item, stall=stall)
    stock.reserved_quantity = max(stock.reserved_quantity - quantity, 0)
    stock.save(update_fields=["reserved_quantity"])
    return stock


@transaction.atomic
def consume_reserved_stock(item, stall, quantity):
    stock = Stock.objects.select_for_update().get(item=item, stall=stall)
    if stock.reserved_quantity < quantity:
        raise ValidationError(f"Reserved stock mismatch for {item.name}")
    stock.quantity -= quantity
    stock.reserved_quantity -= quantity
    stock.save(update_fields=["quantity", "reserved_quantity"])
    return stock


@transaction.atomic
def ensure_sub_stall_stock():
    try:
        sub_stall = Stall.objects.get(name="Sub")
    except Stall.DoesNotExist:
        print("Sub Stall not found")
        return

    low_stock_threshold = 5
    created_count = 0

    for item in Item.objects.filter(is_deleted=False):
        stock, created = Stock.objects.get_or_create(
            item=item,
            stall=sub_stall,
            defaults={"quantity": 0, "low_stock_threshold": low_stock_threshold},
        )
        if created:
            created_count += 1

    print(f"Created {created_count} stock records for Sub Stall")
