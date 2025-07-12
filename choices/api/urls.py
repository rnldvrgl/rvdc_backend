from django.urls import path
from choices.api.views import (
    ItemChoicesAPIView,
    StallChoicesAPIView,
    ProductCategoryChoicesAPIView,
    ClientChoicesAPIView,
    TechnicianChoicesAPIView,
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
]
