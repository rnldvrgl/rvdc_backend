from django.urls import path
from choices.api.views import (
    ItemChoicesAPIView,
    StallChoicesAPIView,
    ProductCategoryChoicesAPIView,
    ClientChoicesAPIView,
    TechnicianChoicesAPIView,
    UsersChoicesAPIView,
    BanksChoicesAPIView,
    AirconTypesChoicesAPIView,
    AirconBrandsChoicesAPIView,
)

urlpatterns = [
    path(
        "categories/",
        ProductCategoryChoicesAPIView.as_view(),
        name="category_choices",
    ),
    path("items/", ItemChoicesAPIView.as_view(), name="item_choices"),
    path("stalls/", StallChoicesAPIView.as_view(), name="stall_choices"),
    path("clients/", ClientChoicesAPIView.as_view(), name="client_choices"),
    path("technicians/", TechnicianChoicesAPIView.as_view(), name="technician_choices"),
    path("users/", UsersChoicesAPIView.as_view(), name="users_choices"),
    path("banks/", BanksChoicesAPIView.as_view(), name="banks_choices"),
    path(
        "aircon-types/",
        AirconTypesChoicesAPIView.as_view(),
        name="aircon_types_choices",
    ),
    path(
        "aircon-brands/",
        AirconBrandsChoicesAPIView.as_view(),
        name="aircon_brands_choices",
    ),
]
