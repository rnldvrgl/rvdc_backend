from rest_framework.routers import DefaultRouter

from .views import (
	QuotationPriceListTemplateViewSet,
	QuotationTermsTemplateViewSet,
	QuotationViewSet,
)

router = DefaultRouter()
router.register(r"templates", QuotationTermsTemplateViewSet, basename="quotation-template")
router.register(r"price-list-templates", QuotationPriceListTemplateViewSet, basename="quotation-price-list-template")
router.register(r"", QuotationViewSet, basename="quotation")

urlpatterns = router.urls
