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
    path("stocks/", StockListCreateView.as_view(), name="stock-list-create"),
    path("stocks/<int:pk>/", StockDetailView.as_view(), name="stock-detail"),
    path(
        "categories/",
        ProductCategoryListCreateView.as_view(),
        name="category-list-create",
    ),
    path(
        "stock-room/", StockRoomStockListCreateView.as_view(), name="stock-room-stock"
    ),
    path(
        "stock-room/<int:pk>/",
        StockRoomStockDetailView.as_view(),
        name="stockroom-stock-detail",
    ),
    path("stock-transfer/", StockTransferCreateView.as_view(), name="stock-transfer"),
]
