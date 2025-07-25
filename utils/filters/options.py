from typing import List, Dict
from inventory.models import Item


def get_status_options() -> List[Dict[str, str]]:
    return [
        {"label": "No Stock", "value": "no_stock"},
        {"label": "Low Stock", "value": "low_stock"},
        {"label": "High Stock", "value": "high_stock"},
    ]


def get_unit_of_measure_options() -> List[Dict[str, str]]:
    units = (
        Item.objects.order_by("unit_of_measure")
        .values_list("unit_of_measure", flat=True)
        .distinct()
        .exclude(unit_of_measure__isnull=True)
        .exclude(unit_of_measure__exact="")
    )
    return [{"label": u, "value": u} for u in units]
