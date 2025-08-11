from django.urls import path, include
from rest_framework.routers import DefaultRouter
from clients.api.views import ClientViewSet

router = DefaultRouter()
router.register("", ClientViewSet, basename="client")

urlpatterns = [
    path("", include(router.urls)),
]
