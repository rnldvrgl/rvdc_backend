from rest_framework.routers import DefaultRouter
from services.api.views import (
    ServiceViewSet,
    ServiceApplianceViewSet,
    ApplianceItemUsedViewSet,
    ServiceItemUsedViewSet,
    ServiceExtraChargeViewSet,
    ServiceReceiptViewSet,
    TechnicianAssignmentViewSet,
    ApplianceTypeViewSet,
    CompanyAssetViewSet,
    JobOrderTemplatePrintViewSet,
    ServicePartTemplateViewSet,
)

router = DefaultRouter()
router.register(r"services", ServiceViewSet, basename="service")
router.register(
    r"service-appliances", ServiceApplianceViewSet, basename="service-appliance"
)
router.register(r"appliance-items", ApplianceItemUsedViewSet, basename="appliance-item")
router.register(r"service-items", ServiceItemUsedViewSet, basename="service-item")
router.register(r"service-extra-charges", ServiceExtraChargeViewSet, basename="service-extra-charge")
router.register(r"service-receipts", ServiceReceiptViewSet, basename="service-receipt")
router.register(
    r"technician-assignments",
    TechnicianAssignmentViewSet,
    basename="technician-assignment",
)
router.register(r"appliance-types", ApplianceTypeViewSet, basename="appliance-type")
router.register(r"company-assets", CompanyAssetViewSet, basename="company-asset")
router.register(
    r"jo-template-prints",
    JobOrderTemplatePrintViewSet,
    basename="jo-template-print",
)
router.register(
    r"service-part-templates",
    ServicePartTemplateViewSet,
    basename="service-part-template",
)

urlpatterns = router.urls
