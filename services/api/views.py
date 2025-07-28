from rest_framework import viewsets, filters as drf_filters, generics
from django_filters.rest_framework import DjangoFilterBackend
from services.models import *
from services.api.serializers import *
from services.api.filters import *


# Top-level viewsets
class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all().order_by("-created_at")
    serializer_class = ServiceSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.OrderingFilter]
    filterset_class = ServiceFilter
    ordering_fields = ["created_at", "status"]


class ServiceApplianceViewSet(viewsets.ModelViewSet):
    queryset = ServiceAppliance.objects.all()
    serializer_class = ServiceApplianceSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.OrderingFilter]
    filterset_class = ServiceApplianceFilter
    ordering_fields = ["status"]


class ApplianceItemUsedViewSet(viewsets.ModelViewSet):
    queryset = ApplianceItemUsed.objects.select_related("appliance", "item").all()
    serializer_class = ApplianceItemUsedSerializer


class AirconInstallationViewSet(viewsets.ModelViewSet):
    queryset = AirconInstallation.objects.select_related("service").all()
    serializer_class = AirconInstallationSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.OrderingFilter]
    filterset_class = AirconInstallationFilter
    ordering_fields = ["id"]


class AirconItemUsedViewSet(viewsets.ModelViewSet):
    queryset = AirconItemUsed.objects.select_related("installation", "item").all()
    serializer_class = AirconItemUsedSerializer


class HomeServiceScheduleViewSet(viewsets.ModelViewSet):
    queryset = HomeServiceSchedule.objects.select_related("service").all()
    serializer_class = HomeServiceScheduleSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.OrderingFilter]
    filterset_class = HomeServiceScheduleFilter
    ordering_fields = ["scheduled_date"]


class ServiceStatusHistoryViewSet(viewsets.ModelViewSet):
    queryset = ServiceStatusHistory.objects.select_related("service").all()
    serializer_class = ServiceStatusHistorySerializer


class ApplianceStatusHistoryViewSet(viewsets.ModelViewSet):
    queryset = ApplianceStatusHistory.objects.select_related("appliance").all()
    serializer_class = ApplianceStatusHistorySerializer


class MotorRewindViewSet(viewsets.ModelViewSet):
    queryset = MotorRewind.objects.select_related("service", "appliance_type").all()
    serializer_class = MotorRewindSerializer
    filter_backends = [DjangoFilterBackend, drf_filters.OrderingFilter]
    filterset_class = MotorRewindFilter
    ordering_fields = ["created_at"]


# Nested ViewSets
class NestedServiceApplianceViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceApplianceSerializer

    def get_queryset(self):
        return ServiceAppliance.objects.filter(service_id=self.kwargs["service_pk"])


class NestedMotorRewindViewSet(viewsets.ModelViewSet):
    serializer_class = MotorRewindSerializer

    def get_queryset(self):
        return MotorRewind.objects.filter(service_id=self.kwargs["service_pk"])


class NestedAirconInstallationViewSet(viewsets.ModelViewSet):
    serializer_class = AirconInstallationSerializer

    def get_queryset(self):
        return AirconInstallation.objects.filter(service_id=self.kwargs["service_pk"])


class NestedHomeServiceScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = HomeServiceScheduleSerializer

    def get_queryset(self):
        return HomeServiceSchedule.objects.filter(service_id=self.kwargs["service_pk"])


# Custom scheduled services list
class ScheduledHomeServiceListAPIView(generics.ListAPIView):
    serializer_class = HomeServiceScheduleSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = HomeServiceScheduleFilter

    def get_queryset(self):
        return HomeServiceSchedule.objects.select_related("service").order_by(
            "scheduled_date"
        )
