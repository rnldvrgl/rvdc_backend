from installations.api.views import (
    AirconBrandViewSet,
    AirconInstallationViewSet,
    AirconModelViewSet,
    AirconUnitViewSet,
    WarrantyClaimViewSet,
)
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r"aircon-brands", AirconBrandViewSet, basename="aircon-brand")
router.register(r"aircon-models", AirconModelViewSet, basename="aircon-model")
router.register(r"aircon-units", AirconUnitViewSet, basename="aircon-unit")
router.register(
    r"aircon-installations", AirconInstallationViewSet, basename="aircon-installation"
)
router.register(r"warranty-claims", WarrantyClaimViewSet, basename="warranty-claim")

urlpatterns = router.urls
