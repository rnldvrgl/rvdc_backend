from rest_framework.routers import DefaultRouter
from receivables.api.views import ChequeCollectionViewSet

router = DefaultRouter()
router.register(r"cheques", ChequeCollectionViewSet, basename="cheque")

urlpatterns = router.urls
