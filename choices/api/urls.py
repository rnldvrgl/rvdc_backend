from choices.api.views import (
    AirconBrandsChoicesAPIView,
    AirconTypesChoicesAPIView,
    ApplianceTypesChoicesAPIView,
    BanksChoicesAPIView,
    ClientChoicesAPIView,
    EmployeesChoicesAPIView,
    ExpenseCategoriesChoicesAPIView,
    ItemChoicesAPIView,
    ProductCategoryChoicesAPIView,
    StallChoicesAPIView,
    TechniciansChoicesAPIView,
    UsersChoicesAPIView,
)
from django.urls import path

urlpatterns = [
    path(
        "categories/",
        ProductCategoryChoicesAPIView.as_view(),
        name="category_choices",
    ),
    path("items/", ItemChoicesAPIView.as_view(), name="item_choices"),
    path("stalls/", StallChoicesAPIView.as_view(), name="stall_choices"),
    path("clients/", ClientChoicesAPIView.as_view(), name="client_choices"),
    path("employees/", EmployeesChoicesAPIView.as_view(), name="employee_choices"),
    path("technicians/", TechniciansChoicesAPIView.as_view(), name="technicians_choices"),
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
    path(
        "expense-categories/",
        ExpenseCategoriesChoicesAPIView.as_view(),
        name="expense_categories_choices",
    ),
    path(
        "appliance-types/",
        ApplianceTypesChoicesAPIView.as_view(),
        name="appliance_types_choices",
    ),
    path("users/", UsersChoicesAPIView.as_view(), name="users_choices"),
]
