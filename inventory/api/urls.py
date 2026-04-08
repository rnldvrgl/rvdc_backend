from django.urls import include, path
from inventory.api.export_views import InventoryExportView
from inventory.api.views import (
    CustomItemTemplateViewSet,
    DirectStockRequestBatchViewSet,
    ItemViewSet,
    ProductCategoryViewSet,
    StallViewSet,
    StockRequestViewSet,
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
router.register(r"stock-requests", StockRequestViewSet, basename="stockrequest")
router.register(r"direct-stock-batches", DirectStockRequestBatchViewSet, basename="directstockbatch")
router.register(r"custom-item-templates", CustomItemTemplateViewSet, basename="customitemtemplate")

urlpatterns = [
    path("", include(router.urls)),
    path("export-report/", InventoryExportView.as_view(), name="inventory-export-report"),
]
