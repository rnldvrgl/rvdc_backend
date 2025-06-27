from django.urls import path
from inventory.api.views import (
    ProductCategoryListCreateView,
    ItemListCreateView,
    ItemDetailView,
    StallListCreateView,
    StallDetailView,
    StockListCreateView,
    StockDetailView,
    StockRoomStockListCreateView,
    StockRoomStockDetailView,
    StockTransferCreateView,
)

urlpatterns = [
    path("items/", ItemListCreateView.as_view(), name="item-list-create"),
    path("items/<int:pk>/", ItemDetailView.as_view(), name="item-detail"),
    path("stalls/", StallListCreateView.as_view(), name="stall-list-create"),
    path("stalls/<int:pk>/", StallDetailView.as_view(), name="stall-detail"),
    path("stocks/stall/", StockListCreateView.as_view(), name="stock-list-create"),
    path("stocks/stall/<int:pk>/", StockDetailView.as_view(), name="stock-detail"),
    path(
        "categories/",
        ProductCategoryListCreateView.as_view(),
        name="category-list-create",
    ),
    path(
        "stocks/management/",
        StockRoomStockListCreateView.as_view(),
        name="stock-room-stock",
    ),
    path(
        "stocks/management/<int:pk>/",
        StockRoomStockDetailView.as_view(),
        name="stockroom-stock-detail",
    ),
    path("stocks/transfer/", StockTransferCreateView.as_view(), name="stock-transfer"),
]
