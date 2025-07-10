from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sales.api.views import SalesTransactionViewSet

router = DefaultRouter()
router.register(r"transactions", SalesTransactionViewSet, basename="sales-transaction")

urlpatterns = [
    path("", include(router.urls)),
]
