from django.db import transaction


def record_stock_movement(
    item,
    stall,
    quantity,
    movement_type,
    note="",
    related_object=None,
):
    from inventory.models import StockMovement

    MOVEMENT_TYPE_CHOICES = {
        "sale",
        "purchase",
        "transfer_in",
        "transfer_out",
        "adjustment",
        "return",
        "restore_sale",
        "void_sale",
    }

    if movement_type not in MOVEMENT_TYPE_CHOICES:
        raise ValueError(
            f"Invalid movement_type '{movement_type}'. "
            f"Allowed: {sorted(MOVEMENT_TYPE_CHOICES)}"
        )

    return StockMovement.objects.create(
        item=item,
        stall=stall,
        quantity=quantity,
        note=note,
        movement_type=movement_type,
        related_object=related_object,
    )


def user_can_manage_stall(user, stall):
    """
    Checks if a user has permission to manage a stall.
    """
    return user.role == "admin" or user.assigned_stall == stall


@transaction.atomic
def create_item_with_initial_stock(validated_data, user=None):
    from inventory.models import Item, StockRoomStock, Stock, Stall

    """
    Creates an Item, initializes StockRoomStock with initial quantity,
    logs StockMovement, and sets zero stock for all stalls.

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

    # Log StockMovement for initial stock only in stock room
    if initial_stock_quantity > 0:
        record_stock_movement(
            item=item,
            stall=None,
            quantity=initial_stock_quantity,
            movement_type="purchase",
            note="Initial stock in stock room",
        )

    # Create zero Stock entries for each stall (no stock movement needed)
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
    from inventory.models import Item, Stock, Stall

    """
    Creates a Stall and sets up zero stock for all existing items.

    validated_data: dict with keys:
        - name, location, low_stock_threshold
    """
    low_stock_threshold = validated_data.get("low_stock_threshold", 5)
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
