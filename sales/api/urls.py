from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sales.api.views import SalesTransactionViewSet
from analytics.api.export_views import SalesExportView

router = DefaultRouter()
router.register(r"transactions", SalesTransactionViewSet, basename="sales-transaction")

urlpatterns = [
    path("export-report/", SalesExportView.as_view(), name="sales-export"),
    path("", include(router.urls)),
]
