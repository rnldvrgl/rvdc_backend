from rest_framework import viewsets, filters
from services.models import ServiceRequest, ServiceStep, ServiceRequestItem
from .serializers import (
    ServiceRequestSerializer,
    ServiceStepSerializer,
)
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend


class ServiceRequestViewSet(viewsets.ModelViewSet):
    queryset = ServiceRequest.objects.all().order_by("-date_received")
    serializer_class = ServiceRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["client__full_name", "client__phone"]
    search_fields = ["client__full_name", "client__phone"]


class ServiceStepViewSet(viewsets.ModelViewSet):
    queryset = ServiceStep.objects.all().order_by("-performed_on")
    serializer_class = ServiceStepSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["service_request__client__full_name", "service_type"]
    search_fields = ["service_request__client__full_name", "service_type"]
