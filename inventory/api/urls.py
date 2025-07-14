from django.urls import path, include
from rest_framework.routers import DefaultRouter
from inventory.api.views import (
    ItemViewSet,
    StallViewSet,
    StockViewSet,
    StockRoomStockViewSet,
    ProductCategoryViewSet,
    StockTransferViewSet,
)

router = DefaultRouter()
router.register(r"items", ItemViewSet)
router.register(r"stalls", StallViewSet)
router.register(r"stocks", StockViewSet)
router.register(r"stockroom/stocks", StockRoomStockViewSet, basename="stockroomstock")
router.register(r"categories", ProductCategoryViewSet)
router.register(r"stock-transfers", StockTransferViewSet, basename="stocktransfer")

urlpatterns = [
    path("", include(router.urls)),
]
