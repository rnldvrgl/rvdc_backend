from rest_framework.routers import DefaultRouter
from remittances.api.views import RemittanceRecordViewSet

router = DefaultRouter()
router.register(r"", RemittanceRecordViewSet, basename="remittances")

urlpatterns = router.urls
