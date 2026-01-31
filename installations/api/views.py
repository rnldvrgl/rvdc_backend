from django_filters.rest_framework import DjangoFilterBackend
from installations.api.filters import (
    AirconInstallationFilter,
    AirconModelFilter,
    AirconUnitFilter,
)
from installations.api.serializers import (
    AirconBrandSerializer,
    AirconInstallationCreateSerializer,
    AirconInstallationSerializer,
    AirconModelSerializer,
    AirconReservationSerializer,
    AirconSaleSerializer,
    AirconUnitSerializer,
)
from installations.models import (
    AirconBrand,
    AirconInstallation,
    AirconModel,
    AirconUnit,
)
from rest_framework import filters as drf_filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.filters.options import (
    get_aircon_brand_options,
    get_aircon_model_options,
    get_aircon_type_options,
)
from utils.filters.role_filters import get_role_based_filter_response
from utils.query import (
    get_role_filtered_queryset,
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
    search_fields = ["name"]
    ordering_fields = ["name"]

    def get_queryset(self):
        return get_role_filtered_queryset(self.request, super().get_queryset())


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
            "aircon_type": {"options": get_aircon_type_options},
            "is_inverter": {
                "options": lambda: [
                    {"label": "Yes", "value": "true"},
                    {"label": "No", "value": "false"},
                ]
            },
            "has_discount": {
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
    """
    Aircon unit operations with sales and installation workflows.

    Endpoints:
    - GET /aircon-units/ - List all units
    - POST /aircon-units/ - Create new unit
    - GET /aircon-units/{id}/ - Get unit details
    - PUT/PATCH /aircon-units/{id}/ - Update unit
    - DELETE /aircon-units/{id}/ - Delete unit
    - GET /aircon-units/available/ - List available units for sale
    - POST /aircon-units/sell/ - Sell one or more units
    - POST /aircon-units/{id}/reserve/ - Reserve a unit for a client
    - POST /aircon-units/{id}/release-reservation/ - Release reservation
    - POST /aircon-units/{id}/create-installation/ - Create installation service
    - GET /aircon-units/stock-report/ - Get inventory stock report
    """

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

    @action(detail=False, methods=["get"], url_path="available")
    def available_units(self, request):
        """
        Get available units for sale.

        Query params:
        - model: Filter by model ID
        - brand: Filter by brand ID
        """
        from installations.business_logic import AirconInventoryManager

        model_id = request.query_params.get('model')
        brand_id = request.query_params.get('brand')

        model = None
        brand = None

        if model_id:
            from installations.models import AirconModel
            try:
                model = AirconModel.objects.get(id=model_id)
            except AirconModel.DoesNotExist:
                pass

        if brand_id:
            from installations.models import AirconBrand
            try:
                brand = AirconBrand.objects.get(id=brand_id)
            except AirconBrand.DoesNotExist:
                pass

        units = AirconInventoryManager.get_available_units(model=model, brand=brand)
        serializer = self.get_serializer(units, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="sell")
    def sell_units(self, request):
        """
        Sell one or more aircon units.

        Request body:
        {
            "unit_ids": [1, 2, 3],
            "client_id": 123,
            "payment_type": "cash"
        }

        Response:
        {
            "units": [...],
            "sale_transaction": {...},
            "total_amount": "50000.00"
        }
        """
        serializer = AirconSaleSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        # Return sale details
        return Response({
            'units': AirconUnitSerializer(result.get('units') or [result.get('unit')], many=True).data,
            'sale_transaction_id': result['sale_transaction'].id if result.get('sale_transaction') else None,
            'total_amount': str(result.get('total_amount') or result.get('sale_price')),
            'client_id': result['client'].id,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="reserve")
    def reserve_unit(self, request, pk=None):
        """
        Reserve a unit for a client.

        Request body:
        {
            "client_id": 123
        }
        """
        unit = self.get_object()

        data = {
            'unit_id': unit.id,
            'client_id': request.data.get('client_id')
        }

        serializer = AirconReservationSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(
            AirconUnitSerializer(result).data,
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"], url_path="release-reservation")
    def release_reservation(self, request, pk=None):
        """Release reservation on a unit."""
        from installations.business_logic import AirconInventoryManager

        unit = self.get_object()

        if not unit.is_reserved:
            return Response(
                {'error': 'Unit is not reserved.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        result = AirconInventoryManager.release_reservation(unit)

        return Response(
            AirconUnitSerializer(result).data,
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"], url_path="create-installation")
    def create_installation(self, request, pk=None):
        """
        Create installation service for a sold unit.

        Request body:
        {
            "scheduled_date": "2024-01-15",
            "scheduled_time": "14:00:00",
            "labor_fee": "500.00",
            "apply_free_installation": false,
            "copper_tube_length": 25
        }
        """
        unit = self.get_object()

        data = request.data.copy()
        data['unit_id'] = unit.id

        serializer = AirconInstallationCreateSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response({
            'service_id': result['service'].id,
            'installation_id': result['installation'].id,
            'unit_id': result['unit'].id,
            'appliance_id': result['appliance'].id,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="stock-report")
    def stock_report(self, request):
        """
        Get aircon unit inventory stock report.

        Query params:
        - model: Filter by model ID

        Response:
        {
            "total": 100,
            "available": 75,
            "reserved": 10,
            "sold": 15
        }
        """
        from installations.business_logic import AirconInventoryManager

        model_id = request.query_params.get('model')
        model = None

        if model_id:
            from installations.models import AirconModel
            try:
                model = AirconModel.objects.get(id=model_id)
            except AirconModel.DoesNotExist:
                pass

        report = AirconInventoryManager.check_stock_level(model=model)

        return Response(report, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "model": {"options": get_aircon_model_options},
            "sale": {"options": lambda: []},
            "installation": {"options": lambda: []},
            "reserved_by": {"options": lambda: []},
            "is_available_for_sale": {
                "options": lambda: [
                    {"label": "Available", "value": "true"},
                    {"label": "Not Available", "value": "false"},
                ]
            },
            "is_sold": {
                "options": lambda: [
                    {"label": "Sold", "value": "true"},
                    {"label": "Not Sold", "value": "false"},
                ]
            },
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
