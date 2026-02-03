from django.urls import include, path
from inventory.api.views import (
    ItemViewSet,
    ProductCategoryViewSet,
    StallViewSet,
    StockRoomStockViewSet,
    StockViewSet,
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r"items", ItemViewSet)
router.register(r"stalls", StallViewSet)
router.register(r"stocks", StockViewSet)
router.register(r"stockroom/stocks", StockRoomStockViewSet, basename="stockroomstock")
router.register(r"categories", ProductCategoryViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
