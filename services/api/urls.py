from rest_framework.routers import DefaultRouter
from services.api.views import (
    ServiceViewSet,
    ServiceApplianceViewSet,
    ApplianceItemUsedViewSet,
    TechnicianAssignmentViewSet,
)

router = DefaultRouter()
router.register(r"services", ServiceViewSet, basename="service")
router.register(
    r"service-appliances", ServiceApplianceViewSet, basename="service-appliance"
)
router.register(r"appliance-items", ApplianceItemUsedViewSet, basename="appliance-item")
router.register(
    r"technician-assignments",
    TechnicianAssignmentViewSet,
    basename="technician-assignment",
)

urlpatterns = router.urls
