from rest_framework.routers import DefaultRouter
from sales.api.views import SalesTransactionViewSet

router = DefaultRouter()
router.register("transactions", SalesTransactionViewSet, basename="transactions")

urlpatterns = router.urls
