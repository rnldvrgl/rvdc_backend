from django.urls import include, path
from rest_framework.routers import DefaultRouter
from schedules.api.views import ScheduleViewSet

router = DefaultRouter()
router.register("", ScheduleViewSet, basename="schedule")

urlpatterns = [
    path("", include(router.urls)),
]
