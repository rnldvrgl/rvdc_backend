from django.urls import path
from inventory.api.views import (
    ItemListCreateView,
    ItemDetailView,
    StallListCreateView,
    StallDetailView,
    StockListCreateView,
    StockDetailView,
    StockRoomStockListCreateView,
    StockRoomStockDetailView,
    StockTransferCreateView,
    StockTransferListRelatedToMyStallView,
    StockAdjustAPIView,
    StockRestockAPIView,
    ItemChoicesAPIView,
    StallChoicesAPIView,
    ProductCategoryChoicesAPIView,
    ProductCategoryListCreateView,
    ProductCategoryDetailView,
)

urlpatterns = [
    # Product categories
    path(
        "categories/",
        ProductCategoryListCreateView.as_view(),
        name="category_list_create",
    ),
    path(
        "categories/<int:pk>/",
        ProductCategoryDetailView.as_view(),
        name="category_detail",
    ),
    # Items
    path("items/", ItemListCreateView.as_view(), name="item_list_create"),
    path("items/<int:pk>/", ItemDetailView.as_view(), name="item_detail"),
    # Stalls
    path(
        "stalls/stocks/",
        StockListCreateView.as_view(),
        name="stall_stock_list_create_view",
    ),
    path("stalls/", StallListCreateView.as_view(), name="stall_list_create"),
    path("stalls/<int:pk>/", StallDetailView.as_view(), name="stall_detail"),
    # Stocks at stalls (nested)
    path(
        "stalls/<int:stall_id>/stocks/",
        StockListCreateView.as_view(),
        name="stock_list_create",
    ),
    path(
        "stalls/<int:stall_id>/stocks/<int:pk>/",
        StockDetailView.as_view(),
        name="stock_detail",
    ),
    path(
        "stalls/<int:stall_id>/stocks/<int:stock_id>/restock/",
        StockRestockAPIView.as_view(),
        name="stock_restock",
    ),
    # Stocks in stock room (management)
    path(
        "stocks/management/",
        StockRoomStockListCreateView.as_view(),
        name="stock_room_stock_list_create",
    ),
    path(
        "stocks/management/<int:pk>/",
        StockRoomStockDetailView.as_view(),
        name="stock_room_stock_detail",
    ),
    # Stock transfers & adjustments
    path(
        "stocks/transfer/",
        StockTransferCreateView.as_view(),
        name="stock_transfer_create",
    ),
    path(
        "stocks/transfers/",
        StockTransferListRelatedToMyStallView.as_view(),
        name="stock_transfer_list",
    ),
    path("stocks/adjust/", StockAdjustAPIView.as_view(), name="stock_adjust"),
    # Dropdown choices (for forms)
    path(
        "choices/categories/",
        ProductCategoryChoicesAPIView.as_view(),
        name="category_choices",
    ),
    path("choices/items/", ItemChoicesAPIView.as_view(), name="item_choices"),
    path("choices/stalls/", StallChoicesAPIView.as_view(), name="stall_choices"),
]
