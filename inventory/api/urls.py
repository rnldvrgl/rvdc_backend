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
    StockRoomRestockAPIView,
)

urlpatterns = [
    # --------------------------------------
    # PRODUCT CATEGORIES
    # --------------------------------------
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
    # --------------------------------------
    # ITEMS
    # --------------------------------------
    path("items/", ItemListCreateView.as_view(), name="item_list_create"),
    path("items/<int:pk>/", ItemDetailView.as_view(), name="item_detail"),
    # --------------------------------------
    # STALLS
    # --------------------------------------
    path("stalls/", StallListCreateView.as_view(), name="stall_list_create"),
    path("stalls/<int:pk>/", StallDetailView.as_view(), name="stall_detail"),
    # --------------------------------------
    # STOCKS AT STALLS (flattened)
    # --------------------------------------
    path("stocks/", StockListCreateView.as_view(), name="stock_list_create"),
    path("stocks/<int:pk>/", StockDetailView.as_view(), name="stock_detail"),
    path(
        "stocks/<int:stock_id>/restock/",
        StockRestockAPIView.as_view(),
        name="stock_restock",
    ),
    # --------------------------------------
    # STOCK ROOM STOCKS (for management)
    # --------------------------------------
    path(
        "stockroom/stocks/<int:stock_id>/restock/",
        StockRoomRestockAPIView.as_view(),
        name="stock_room_stock_restock",
    ),
    path(
        "stockroom/stocks/",
        StockRoomStockListCreateView.as_view(),
        name="stock_room_stock_list_create",
    ),
    path(
        "stockroom/stocks/<int:pk>/",
        StockRoomStockDetailView.as_view(),
        name="stock_room_stock_detail",
    ),
    # --------------------------------------
    # STOCK TRANSFERS & ADJUSTMENTS
    # --------------------------------------
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
    # --------------------------------------
    # SIMPLE DROPDOWN CHOICES
    # --------------------------------------
    path(
        "choices/categories/",
        ProductCategoryChoicesAPIView.as_view(),
        name="category_choices",
    ),
    path("choices/items/", ItemChoicesAPIView.as_view(), name="item_choices"),
    path("choices/stalls/", StallChoicesAPIView.as_view(), name="stall_choices"),
]
