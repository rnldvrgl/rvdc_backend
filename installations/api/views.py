from django_filters.rest_framework import DjangoFilterBackend
from installations.api.filters import (
    AirconModelFilter,
    AirconUnitFilter,
)
from installations.api.serializers import (
    AirconBrandSerializer,
    AirconInstallationCreateSerializer,
    AirconModelSerializer,
    AirconReservationSerializer,
    AirconSaleSerializer,
    AirconUnitSerializer,
    FreeCleaningEligibilitySerializer,
    FreeCleaningRedemptionSerializer,
    WarrantyClaimApproveSerializer,
    WarrantyClaimCancelSerializer,
    WarrantyClaimCreateSerializer,
    WarrantyClaimRejectSerializer,
    WarrantyClaimSerializer,
    WarrantyEligibilitySerializer,
)
from installations.models import (
    AirconBrand,
    AirconModel,
    AirconUnit,
    WarrantyClaim,
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
from utils.soft_delete import SoftDeleteViewSetMixin


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

    # No role filtering - brands are global resources


class AirconModelViewSet(viewsets.ModelViewSet):
    queryset = AirconModel.objects.select_related('brand').prefetch_related('price_history').all()
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

    # No role filtering - models are global resources

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


class AirconUnitViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    """
    Aircon unit inventory management.
    """
    allow_hard_delete = True
    """
    
    This viewset manages the inventory of aircon units available for installation.
    Units are added to inventory and later linked to sales/installations through
    the installation workflow.

    Endpoints:
    - GET /aircon-units/ - List all units in inventory
          Query params:
          - is_available_for_sale=true: Units available to purchase
          - is_available_for_installation=true: Units available for installation scheduling
          - is_reserved=true/false: Filter by reservation status
    - POST /aircon-units/ - Add new unit to inventory
    - GET /aircon-units/{id}/ - Get unit details
    - PUT/PATCH /aircon-units/{id}/ - Update unit information
    - DELETE /aircon-units/{id}/ - Remove unit from inventory
    - GET /aircon-units/available/ - List available units for sale
    - POST /aircon-units/sell/ - Sell one or more units (creates sale transaction)
    - POST /aircon-units/{id}/reserve/ - Reserve a unit for a client
    - POST /aircon-units/{id}/release-reservation/ - Release reservation
    - POST /aircon-units/{id}/create-installation/ - Create installation service (reserves unit if not sold)
    - GET /aircon-units/stock-report/ - Get inventory stock report
    """

    queryset = AirconUnit.objects.select_related(
        'model__brand', 'stall', 'installation_service', 'installation_service__client',
        'reserved_by', 'sale__client'
    ).prefetch_related(
        'model__price_history',
    ).all()
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
    ordering = ["-created_at"]

    def get_queryset(self):
        return get_role_filtered_queryset(
            self.request, super().get_queryset().filter(is_deleted=False)
        )

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
            "is_sold": {
                "options": lambda: [
                    {"label": "Sold", "value": "true"},
                    {"label": "Not Sold", "value": "false"},
                ]
            },
            "is_installed": {
                "options": lambda: [
                    {"label": "Installed", "value": "true"},
                    {"label": "Not Installed", "value": "false"},
                ]
            },
            "is_available": {
                "options": lambda: [
                    {"label": "Available", "value": "true"},
                    {"label": "Not Available", "value": "false"},
                ]
            },
        }
        ordering_config = [
            {"label": "Serial Number", "value": "serial_number"},
            {"label": "Created At", "value": "created_at"},
        ]
        return get_role_based_filter_response(request, filters_config, ordering_config)


class WarrantyClaimViewSet(viewsets.ModelViewSet):
    """
    Warranty claim management and free cleaning redemption.

    Endpoints:
    - GET /warranty-claims/ - List all warranty claims
    - POST /warranty-claims/ - Create new warranty claim
    - GET /warranty-claims/{id}/ - Get claim details
    - PUT/PATCH /warranty-claims/{id}/ - Update claim
    - DELETE /warranty-claims/{id}/ - Delete claim
    - POST /warranty-claims/{id}/approve/ - Approve claim and create service
    - POST /warranty-claims/{id}/reject/ - Reject claim with reason
    - POST /warranty-claims/{id}/cancel/ - Cancel claim
    - POST /warranty-claims/{id}/complete/ - Mark claim as completed
    - POST /warranty-claims/check-eligibility/ - Check warranty eligibility
    - POST /warranty-claims/redeem-free-cleaning/ - Redeem free cleaning
    - POST /warranty-claims/check-free-cleaning/ - Check free cleaning eligibility
    """

    queryset = WarrantyClaim.objects.all()
    serializer_class = WarrantyClaimSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter,
    ]
    search_fields = [
        "unit__serial_number",
        "unit__model__name",
        "unit__sale__client__name",
        "issue_description",
    ]
    ordering_fields = ["claim_date", "status", "created_at"]
    filterset_fields = ["status", "claim_type", "unit", "is_valid_claim"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'unit',
            'unit__model',
            'unit__model__brand',
            'unit__sale',
            'unit__sale__client',
            'service',
            'reviewed_by'
        )
        return get_role_filtered_queryset(self.request, queryset, stall_field="unit__stall")

    def create(self, request, *args, **kwargs):
        """
        Create a warranty claim.

        Request body:
        {
            "unit_id": 123,
            "claim_type": "repair",
            "issue_description": "Unit not cooling properly",
            "customer_notes": "Started happening last week"
        }
        """
        serializer = WarrantyClaimCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        claim = serializer.save()

        return Response(
            WarrantyClaimSerializer(claim).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], url_path="approve")
    def approve_claim(self, request, pk=None):
        """
        Approve a warranty claim and optionally create service.

        Request body:
        {
            "technician_assessment": "Confirmed defective compressor",
            "create_service": true,
            "scheduled_date": "2024-01-20",
            "scheduled_time": "10:00:00"
        }
        """
        claim = self.get_object()

        serializer = WarrantyClaimApproveSerializer(
            data=request.data,
            context={'request': request, 'claim': claim}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        response_data = {
            'claim': WarrantyClaimSerializer(result['claim']).data,
        }

        if result.get('service'):
            from services.api.serializers import ServiceSerializer
            response_data['service'] = ServiceSerializer(result['service']).data

        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject_claim(self, request, pk=None):
        """
        Reject a warranty claim.

        Request body:
        {
            "rejection_reason": "Unit damage caused by improper use",
            "is_valid_claim": false
        }
        """
        claim = self.get_object()

        serializer = WarrantyClaimRejectSerializer(
            data=request.data,
            context={'request': request, 'claim': claim}
        )
        serializer.is_valid(raise_exception=True)
        claim = serializer.save()

        return Response(
            WarrantyClaimSerializer(claim).data,
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel_claim(self, request, pk=None):
        """
        Cancel a warranty claim.

        Request body:
        {
            "cancellation_reason": "Customer no longer needs service"
        }
        """
        claim = self.get_object()

        serializer = WarrantyClaimCancelSerializer(
            data=request.data,
            context={'claim': claim}
        )
        serializer.is_valid(raise_exception=True)
        claim = serializer.save()

        return Response(
            WarrantyClaimSerializer(claim).data,
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"], url_path="complete")
    def complete_claim(self, request, pk=None):
        """
        Mark a warranty claim as completed.
        """
        from installations.business_logic import WarrantyClaimManager

        claim = self.get_object()
        claim = WarrantyClaimManager.complete_claim(claim)

        return Response(
            WarrantyClaimSerializer(claim).data,
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["post"], url_path="check-eligibility")
    def check_warranty_eligibility(self, request):
        """
        Check if a unit is eligible for warranty claim.

        Request body:
        {
            "unit_id": 123
        }

        Response:
        {
            "eligible": true,
            "reason": "Unit is under warranty",
            "warranty_days_left": 180,
            "warranty_end_date": "2024-07-15"
        }
        """
        serializer = WarrantyEligibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.check()

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="redeem-free-cleaning")
    def redeem_free_cleaning(self, request):
        """
        Redeem free cleaning for an aircon unit.

        Request body:
        {
            "unit_id": 123,
            "scheduled_date": "2024-01-20",
            "scheduled_time": "14:00:00"
        }

        Response:
        {
            "service": {...},
            "unit": {...}
        }
        """
        serializer = FreeCleaningRedemptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        from services.api.serializers import ServiceSerializer

        return Response({
            'service': ServiceSerializer(result['service']).data,
            'unit': AirconUnitSerializer(result['unit']).data,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="redeem-free-cleaning-batch")
    def redeem_free_cleaning_batch(self, request):
        """
        Redeem free cleaning for multiple aircon units under one client.
        Creates a single cleaning service with all units as appliances.

        Request body:
        {
            "client_id": 1,
            "unit_ids": [1, 2, 3],
            "scheduled_date": "2024-01-20",
            "scheduled_time": "14:00:00"
        }

        Response:
        {
            "service": {...},
            "units": [...]
        }
        """
        from installations.api.serializers import FreeCleaningBatchRedemptionSerializer

        serializer = FreeCleaningBatchRedemptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        from services.api.serializers import ServiceSerializer

        return Response({
            'service': ServiceSerializer(result['service']).data,
            'units': AirconUnitSerializer(result['units'], many=True).data,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="check-free-cleaning")
    def check_free_cleaning_eligibility(self, request):
        """
        Check if a unit is eligible for free cleaning redemption.

        Request body:
        {
            "unit_id": 123
        }

        Response:
        {
            "eligible": true,
            "reason": "Unit is eligible for free cleaning",
            "warranty_days_left": 180
        }
        """
        serializer = FreeCleaningEligibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.check()

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "status": {
                "options": lambda: [
                    {"label": label, "value": value}
                    for value, label in WarrantyClaim.ClaimStatus.choices
                ]
            },
            "claim_type": {
                "options": lambda: [
                    {"label": label, "value": value}
                    for value, label in WarrantyClaim.ClaimType.choices
                ]
            },
            "is_valid_claim": {
                "options": lambda: [
                    {"label": "Valid", "value": "true"},
                    {"label": "Invalid", "value": "false"},
                ]
            },
        }
        ordering_config = [
            {"label": "Claim Date", "value": "claim_date"},
            {"label": "Status", "value": "status"},
            {"label": "Created At", "value": "created_at"},
        ]
        return get_role_based_filter_response(request, filters_config, ordering_config)
