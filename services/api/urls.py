from rest_framework_nested.routers import DefaultRouter, NestedSimpleRouter
from django.urls import path, include
from . import views

router = DefaultRouter()
router.register(r"", views.ServiceViewSet, basename="service")
router.register(r"appliances", views.ServiceApplianceViewSet)
router.register(r"appliance-items-used", views.ApplianceItemUsedViewSet)
router.register(r"aircon-installations", views.AirconInstallationViewSet)
router.register(r"aircon-items-used", views.AirconItemUsedViewSet)
router.register(r"home-schedules", views.HomeServiceScheduleViewSet)
router.register(r"service-status-history", views.ServiceStatusHistoryViewSet)
router.register(r"appliance-status-history", views.ApplianceStatusHistoryViewSet)
router.register(r"motor-rewinds", views.MotorRewindViewSet)


services_router = NestedSimpleRouter(router, r"", lookup="service")
services_router.register(
    r"appliances", views.NestedServiceApplianceViewSet, basename="service-appliances"
)
services_router.register(
    r"motor-rewinds", views.NestedMotorRewindViewSet, basename="service-motor-rewinds"
)
services_router.register(
    r"aircon-installation",
    views.NestedAirconInstallationViewSet,
    basename="service-aircon-installation",
)
services_router.register(
    r"home-schedule",
    views.NestedHomeServiceScheduleViewSet,
    basename="service-home-schedule",
)

urlpatterns = [
    path("", include(router.urls)),
    path("", include(services_router.urls)),
    path(
        "scheduled-home-services/",
        views.ScheduledHomeServiceListAPIView.as_view(),
        name="scheduled-home-services",
    ),
]
