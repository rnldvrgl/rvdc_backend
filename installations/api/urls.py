from rest_framework.routers import DefaultRouter
from installations.api.views import (
    AirconBrandViewSet,
    AirconModelViewSet,
    AirconUnitViewSet,
    AirconInstallationViewSet,
)

router = DefaultRouter()
router.register(r"aircon-brands", AirconBrandViewSet, basename="aircon-brand")
router.register(r"aircon-models", AirconModelViewSet, basename="aircon-model")
router.register(r"aircon-units", AirconUnitViewSet, basename="aircon-unit")
router.register(
    r"aircon-installations", AirconInstallationViewSet, basename="aircon-installation"
)

urlpatterns = router.urls
