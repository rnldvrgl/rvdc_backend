from typing import Dict, List, Optional

from django.db.models import F, Value
from django.db.models.functions import Concat
from installations.models import AirconBrand, AirconModel
from inventory.models import Item, ProductCategory, Stall
from users.models import CustomUser
from utils.enums import AirconType, BankChoices, ServiceMode, ServiceStatus, ServiceType


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


def get_stall_options() -> List[Dict[str, str]]:
    stalls = Stall.objects.filter(is_deleted=False).values("id", "name")
    return [{"label": s["name"], "value": str(s["id"])} for s in stalls]


def get_client_options(include_number: bool = False) -> List[Dict[str, str]]:
    clients = (
        CustomUser.objects.filter(role="client", is_deleted=False)
        .annotate(full_name=Concat(F("first_name"), Value(" "), F("last_name")))
        .values("id", "full_name", "contact_number")
    )

    results = []
    for c in clients:
        label = c["full_name"]
        if include_number and c["contact_number"]:
            label = f"{label} ({c['contact_number']})"

        results.append({"label": label, "value": str(c["id"])})

    return results


def get_user_options(
    include_roles: Optional[list] = None,
    exclude_roles: Optional[list] = None,
) -> List[Dict[str, str]]:
    qs = CustomUser.objects.filter(is_deleted=False)

    if include_roles:
        qs = qs.filter(role__in=include_roles)
    if exclude_roles:
        qs = qs.exclude(role__in=exclude_roles)

    users = qs.annotate(
        full_name=Concat(F("first_name"), Value(" "), F("last_name"))
    ).values("id", "full_name")

    return [{"label": u["full_name"], "value": str(u["id"])} for u in users]


def get_product_category_options() -> List[Dict[str, str]]:
    categories = ProductCategory.objects.filter(is_deleted=False).values("id", "name")
    return [{"label": c["name"], "value": str(c["id"])} for c in categories]


def get_bank_options() -> List[Dict[str, str]]:
    return [{"value": choice.value, "label": choice.label} for choice in BankChoices]


def get_service_status_options():
    return [{"label": label, "value": value} for value, label in ServiceStatus.choices]


def get_service_type_options():
    return [{"label": label, "value": value} for value, label in ServiceType.choices]


def get_service_mode_options():
    return [{"label": label, "value": value} for value, label in ServiceMode.choices]


def get_aircon_type_options():
    return [{"label": label, "value": value} for value, label in AirconType.choices]


def get_aircon_brand_options():
    return [
        {"label": brand.name, "value": str(brand.id)}
        for brand in AirconBrand.objects.all()
    ]


def get_aircon_model_options():
    return [
        {"label": model.name, "value": str(model.id)}
        for model in AirconModel.objects.all()
    ]
