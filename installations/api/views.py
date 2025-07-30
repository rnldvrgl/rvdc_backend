from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as drf_filters
from installations.api.serializers import (
    AirconBrandSerializer,
    AirconModelSerializer,
    AirconInstallationSerializer,
    AirconUnitSerializer,
    AirconItemUsedSerializer,
)
from installations.api.filters import (
    AirconBrandFilter,
    AirconModelFilter,
    AirconInstallationFilter,
    AirconUnitFilter,
)
from installations.models import (
    AirconBrand,
    AirconModel,
    AirconInstallation,
    AirconUnit,
    AirconItemUsed,
)
from utils.query import (
    get_role_filtered_queryset,
)
from utils.filters.role_filters import get_role_based_filter_response
from utils.filters.options import (
    get_aircon_brand_options,
    get_aircon_model_options,
    get_aircon_unit_options,
    get_aircon_installation_options,
    get_item_options,
)


class AirconBrandViewSet(viewsets.ModelViewSet):
    queryset = AirconBrand.objects.all()
    serializer_class = AirconBrandSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter,
    ]
    filterset_class = AirconBrandFilter
    search_fields = ["name"]
    ordering_fields = ["name"]

    def get_queryset(self):
        return get_role_filtered_queryset(self.request, super().get_queryset())

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "name": {"options": get_aircon_brand_options},
        }
        ordering_config = [
            {"label": "Name", "value": "name"},
        ]
        return get_role_based_filter_response(request, filters_config, ordering_config)


class AirconModelViewSet(viewsets.ModelViewSet):
    queryset = AirconModel.objects.all()
    serializer_class = AirconModelSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter,
    ]
    filterset_class = AirconModelFilter
    search_fields = ["name", "brand__name"]
    ordering_fields = ["name", "retail_price"]

    def get_queryset(self):
        return get_role_filtered_queryset(self.request, super().get_queryset())

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "brand": {"options": get_aircon_brand_options},
            "aircon_type": {"options": lambda: []},
            "is_inverter": {
                "options": lambda: [
                    {"label": "Yes", "value": "true"},
                    {"label": "No", "value": "false"},
                ]
            },
        }
        ordering_config = [
            {"label": "Name", "value": "name"},
            {"label": "Retail Price", "value": "retail_price"},
        ]
        return get_role_based_filter_response(request, filters_config, ordering_config)


class AirconUnitViewSet(viewsets.ModelViewSet):
    queryset = AirconUnit.objects.all()
    serializer_class = AirconUnitSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter,
    ]
    filterset_class = AirconUnitFilter
    search_fields = ["serial_number", "model__name", "model__brand__name"]
    ordering_fields = ["serial_number", "created_at"]

    def get_queryset(self):
        return get_role_filtered_queryset(self.request, super().get_queryset())

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "model": {"options": get_aircon_model_options},
            "sale": {"options": lambda: []},
            "installation": {"options": get_aircon_installation_options},
            "reserved_by": {"options": lambda: []},
        }
        ordering_config = [
            {"label": "Serial Number", "value": "serial_number"},
            {"label": "Created At", "value": "created_at"},
        ]
        return get_role_based_filter_response(request, filters_config, ordering_config)


class AirconInstallationViewSet(viewsets.ModelViewSet):
    queryset = AirconInstallation.objects.all()
    serializer_class = AirconInstallationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter,
    ]
    filterset_class = AirconInstallationFilter
    search_fields = ["service__client__full_name", "service__reference_code"]
    ordering_fields = ["id"]

    def get_queryset(self):
        return get_role_filtered_queryset(self.request, super().get_queryset())

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "service": {"options": lambda: []},
        }
        ordering_config = [
            {"label": "ID", "value": "id"},
        ]
        return get_role_based_filter_response(request, filters_config, ordering_config)
