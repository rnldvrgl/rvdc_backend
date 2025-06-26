from rest_framework.routers import DefaultRouter
from .views import (
    ServiceRequestViewSet,
    ServiceStepViewSet,
    ServiceRequestItemViewSet,
)

router = DefaultRouter()
router.register(r"requests", ServiceRequestViewSet)
router.register(r"service-steps", ServiceStepViewSet)
router.register(r"used-items", ServiceRequestItemViewSet)

urlpatterns = router.urls
