from django.db import transaction
from inventory.models import Item, StockRoomStock, Stock, StockMovement, Stall


def record_stock_movement(item, stall, qty, source, related_transfer=None):
    """
    Creates a StockMovement record. If stall is None, indicates stock room.
    """
    StockMovement.objects.create(
        item=item,
        stall=stall,
        quantity=qty,
        source=source,
        related_transfer=related_transfer,
    )


def user_can_manage_stall(user, stall):
    """
    Checks if a user has permission to manage a stall.
    """
    return user.role == "admin" or user.assigned_stall == stall


@transaction.atomic
def create_item_with_initial_stock(validated_data, user=None):
    """
    Creates an Item, initializes StockRoomStock with initial quantity,
    logs StockMovement, and sets zero stock for all stalls.

    validated_data: dict with keys:
        - name, category, srp
        - initial_stock_quantity, low_stock_threshold
    """
    item = Item.objects.create(
        name=validated_data["name"],
        category=validated_data["category"],
        srp=validated_data["srp"],
        unit_of_measure=validated_data.get("unit_of_measure", "pcs"),
        description=validated_data.get("description"),
    )

    initial_stock_quantity = validated_data.get("initial_stock_quantity", 0)
    low_stock_threshold = validated_data.get("low_stock_threshold", 0)

    # Create StockRoomStock with initial quantity
    stock_room_stock = StockRoomStock.objects.create(
        item=item,
        quantity=initial_stock_quantity,
        low_stock_threshold=low_stock_threshold,
    )

    # Create StockMovement for initial stock
    if initial_stock_quantity > 0:
        record_stock_movement(
            item=item,
            stall=None,  # None indicates stock room
            qty=initial_stock_quantity,
            source="stock_room",
            related_transfer=None,
        )

    # Create zero Stock entries for each stall
    for stall in Stall.objects.filter(is_deleted=False):
        Stock.objects.create(
            item=item,
            stall=stall,
            quantity=0,
            low_stock_threshold=low_stock_threshold,
        )

    return item


@transaction.atomic
def create_stall_with_initial_stocks(validated_data):
    """
    Creates a Stall and sets up zero stock for all existing items.

    validated_data: dict with keys:
        - name, location, low_stock_threshold
    """
    low_stock_threshold = validated_data.get("low_stock_threshold", 0)
    stall = Stall.objects.create(
        name=validated_data["name"],
        location=validated_data["location"],
    )

    for item in Item.objects.filter(is_deleted=False):
        Stock.objects.create(
            item=item,
            stall=stall,
            quantity=0,
            low_stock_threshold=low_stock_threshold,
        )

    return stall
