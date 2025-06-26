from rest_framework.routers import DefaultRouter
from .views import ServiceRequestViewSet, ServiceStepViewSet

router = DefaultRouter()
router.register(r"", ServiceRequestViewSet)
router.register(r"steps", ServiceStepViewSet, basename="service-steps")

urlpatterns = router.urls
