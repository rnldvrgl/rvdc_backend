from typing import List, Dict
from inventory.models import Item, Stall, ProductCategory
from django.db.models.functions import Concat
from django.db.models import F, Value
from users.models import CustomUser


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


def get_technician_options() -> List[Dict[str, str]]:
    technicians = (
        CustomUser.objects.filter(role="technician", is_deleted=False)
        .annotate(full_name=Concat(F("first_name"), Value(" "), F("last_name")))
        .values("id", "full_name")
    )
    return [{"label": t["full_name"], "value": str(t["id"])} for t in technicians]


def get_stall_options() -> List[Dict[str, str]]:
    stalls = Stall.objects.filter(is_deleted=False).values("id", "name")
    return [{"label": s["name"], "value": str(s["id"])} for s in stalls]


def get_user_options() -> List[Dict[str, str]]:
    users = (
        CustomUser.objects.filter(role__in=["clerk", "manager"], is_deleted=False)
        .annotate(full_name=Concat(F("first_name"), Value(" "), F("last_name")))
        .values("id", "full_name")
    )
    return [{"label": u["full_name"], "value": str(u["id"])} for u in users]


def get_product_category_options() -> List[Dict[str, str]]:
    categories = ProductCategory.objects.filter(is_deleted=False).values("id", "name")
    return [{"label": c["name"], "value": str(c["id"])} for c in categories]
