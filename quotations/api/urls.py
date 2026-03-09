from rest_framework.routers import DefaultRouter

from .views import QuotationTermsTemplateViewSet, QuotationViewSet

router = DefaultRouter()
router.register(r"templates", QuotationTermsTemplateViewSet, basename="quotation-template")
router.register(r"", QuotationViewSet, basename="quotation")

urlpatterns = router.urls
