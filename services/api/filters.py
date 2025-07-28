from django_filters import rest_framework as filters
from services.models import (
    Service,
    ServiceAppliance,
    AirconInstallation,
    HomeServiceSchedule,
    MotorRewind,
)


class ServiceFilter(filters.FilterSet):
    class Meta:
        model = Service
        fields = ["client", "status", "created_at"]


class ServiceApplianceFilter(filters.FilterSet):
    class Meta:
        model = ServiceAppliance
        fields = ["service", "appliance_type", "status"]


class AirconInstallationFilter(filters.FilterSet):
    class Meta:
        model = AirconInstallation
        fields = ["service", "source"]


class HomeServiceScheduleFilter(filters.FilterSet):
    class Meta:
        model = HomeServiceSchedule
        fields = ["service", "scheduled_date", "scheduled_time"]


class MotorRewindFilter(filters.FilterSet):
    class Meta:
        model = MotorRewind
        fields = ["service", "appliance_type", "created_at"]
