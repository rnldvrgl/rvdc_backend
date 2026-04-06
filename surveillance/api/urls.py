from rest_framework.routers import DefaultRouter
from surveillance.api.views import CCTVCameraViewSet

router = DefaultRouter()
router.register(r"cameras", CCTVCameraViewSet, basename="cctv-camera")

urlpatterns = router.urls
