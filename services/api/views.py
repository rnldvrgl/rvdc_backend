"""
Service API views with two-stall architecture support.

Features:
- Service CRUD operations
- Service completion endpoint (consume stock, create transactions)
- Service cancellation endpoint (release reserved stock)
- Revenue calculation and reporting
"""

from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from services.api.serializers import (
    ApplianceItemUsedSerializer,
    ServiceApplianceSerializer,
    ServiceCancellationSerializer,
    ServiceCompletionSerializer,
    ServiceSerializer,
    TechnicianAssignmentSerializer,
)
from services.business_logic import RevenueCalculator
from services.models import (
    ApplianceItemUsed,
    Service,
    ServiceAppliance,
    TechnicianAssignment,
)
from utils.filters.options import (
    get_client_options,
    get_service_status_options,
    get_service_type_options,
    get_user_options,
)
from utils.filters.role_filters import get_role_based_filter_response
from utils.query import filter_by_date_range


# --------------------------
# Service ViewSet
# --------------------------
class ServiceViewSet(viewsets.ModelViewSet):
    """
    Service operations with two-stall architecture support.

    Endpoints:
    - GET /services/ - List services with filters
    - POST /services/ - Create service (reserves stock)
    - GET /services/{id}/ - Retrieve service details
    - PUT/PATCH /services/{id}/ - Update service
    - DELETE /services/{id}/ - Delete service
    - POST /services/{id}/complete/ - Complete service (consume stock, create transactions)
    - POST /services/{id}/cancel/ - Cancel service (release reserved stock)
    - POST /services/{id}/recalculate_revenue/ - Recalculate revenue attribution
    - GET /services/filters/ - Get filter options
    - GET /services/revenue_report/ - Get revenue summary
    """

    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = (
            Service.objects.all()
            .select_related("client", "stall", "related_transaction")
            .prefetch_related(
                "appliances__items_used__item",
                "appliances__items_used__stall_stock__stall",
                "appliances__appliance_type",
                "technician_assignments__technician",
            )
        )
        return filter_by_date_range(self.request, qs)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """
        Complete a service.

        This endpoint:
        1. Consumes reserved stock (decrements quantity and reserved_quantity)
        2. Creates SalesTransactions for Sub stall (parts sold)
        3. Creates Expenses for Main stall (parts purchased)
        4. Calculates revenue attribution (main vs sub)
        5. Optionally creates unified customer receipt
        6. Updates service status to COMPLETED

        Request body:
        {
            "create_receipt": true  // Optional, default true
        }

        Response:
        {
            "service_id": 123,
            "status": "completed",
            "revenue": {
                "main_revenue": "500.00",
                "sub_revenue": "300.00",
                "total_revenue": "800.00"
            },
            "receipt": 456  // Receipt ID if created
        }
        """
        service = self.get_object()

        serializer = ServiceCompletionSerializer(
            data=request.data,
            context={"service": service, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """
        Cancel a service and release all reserved stock.

        Request body:
        {
            "reason": "Customer cancelled"  // Optional
        }

        Response:
        {
            "service_id": 123,
            "status": "cancelled",
            "released_items": [
                {"item": "Capacitor", "quantity": 2},
                {"item": "Copper Tube", "quantity": 15}
            ]
        }
        """
        service = self.get_object()

        serializer = ServiceCancellationSerializer(
            data=request.data,
            context={"service": service, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="recalculate-revenue")
    def recalculate_revenue(self, request, pk=None):
        """
        Recalculate and update revenue attribution for a service.

        Useful after manual adjustments to labor fees or parts.

        Response:
        {
            "service_id": 123,
            "main_revenue": "500.00",
            "sub_revenue": "300.00",
            "total_revenue": "800.00"
        }
        """
        service = self.get_object()
        revenue_data = RevenueCalculator.calculate_service_revenue(service, save=True)

        return Response(
            {
                "service_id": service.id,
                **revenue_data,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["get"], url_path="revenue-report")
    def revenue_report(self, request):
        """
        Get revenue summary report with main/sub stall breakdown.

        Query params:
        - start_date: Filter services from this date (YYYY-MM-DD)
        - end_date: Filter services to this date (YYYY-MM-DD)
        - status: Filter by service status (e.g., 'completed')

        Response:
        {
            "total_services": 50,
            "completed_services": 45,
            "total_revenue": "25000.00",
            "main_stall_revenue": "15000.00",
            "sub_stall_revenue": "10000.00",
            "services": [...]
        }
        """
        from django.db.models import Count, Sum
        from utils.enums import ServiceStatus

        qs = self.get_queryset()

        # Apply status filter if provided
        service_status = request.query_params.get("status")
        if service_status:
            qs = qs.filter(status=service_status)

        # Calculate aggregates
        aggregates = qs.aggregate(
            total_services=Count("id"),
            completed_count=Count("id", filter=Q(status=ServiceStatus.COMPLETED)),
            total_revenue=Sum("total_revenue"),
            main_revenue=Sum("main_stall_revenue"),
            sub_revenue=Sum("sub_stall_revenue"),
        )

        # Serialize service details
        serializer = self.get_serializer(qs, many=True)

        return Response(
            {
                "total_services": aggregates["total_services"] or 0,
                "completed_services": aggregates["completed_count"] or 0,
                "total_revenue": str(aggregates["total_revenue"] or 0),
                "main_stall_revenue": str(aggregates["main_revenue"] or 0),
                "sub_stall_revenue": str(aggregates["sub_revenue"] or 0),
                "services": serializer.data,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        """Get filter options for service list."""
        filters_config = {
            "client": {"options": get_client_options(include_number=True)},
            "technician": {
                "options": lambda: get_user_options(include_roles=["technician"])
            },
            "status": {"options": get_service_status_options},
            "service_type": {"options": get_service_type_options},
        }

        ordering_config = [
            {"label": "Created At", "value": "created_at"},
            {"label": "Scheduled Date", "value": "scheduled_date"},
            {"label": "Total Revenue", "value": "total_revenue"},
            {"label": "Status", "value": "status"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)


# --------------------------
# Service Appliance ViewSet
# --------------------------
class ServiceApplianceViewSet(viewsets.ModelViewSet):
    """
    Service appliance operations.

    Supports:
    - CRUD operations for appliances within services
    - Promo application (free installation)
    """

    serializer_class = ServiceApplianceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            ServiceAppliance.objects.all()
            .select_related("service", "appliance_type")
            .prefetch_related(
                "items_used__item",
                "items_used__stall_stock__stall",
                "technician_assignments__technician",
            )
        )


# --------------------------
# Appliance Items Used ViewSet
# --------------------------
class ApplianceItemUsedViewSet(viewsets.ModelViewSet):
    """
    Appliance items used operations.

    Supports:
    - CRUD operations for parts used in service appliances
    - Stock reservation/release
    - Promo application (copper tube free 10ft)

    Note: Updates should only be allowed before service completion.
    """

    serializer_class = ApplianceItemUsedSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            ApplianceItemUsed.objects.all()
            .select_related(
                "appliance__service",
                "appliance__appliance_type",
                "item",
                "stall_stock__stall",
                "expense",
            )
        )

    def destroy(self, request, *args, **kwargs):
        """
        Delete an item usage and release reserved stock.
        """
        from services.business_logic import StockReservationManager

        instance = self.get_object()

        # Check if service is already completed
        if hasattr(instance, 'appliance') and hasattr(instance.appliance, 'service'):
            from utils.enums import ServiceStatus

            if instance.appliance.service.status == ServiceStatus.COMPLETED:
                return Response(
                    {"error": "Cannot delete items from a completed service."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Release stock reservation
        if instance.stall_stock:
            StockReservationManager.release_reservation(
                item=instance.item,
                quantity=instance.quantity,
                stall_stock=instance.stall_stock
            )

        return super().destroy(request, *args, **kwargs)


# --------------------------
# Technician Assignment ViewSet
# --------------------------
class TechnicianAssignmentViewSet(viewsets.ModelViewSet):
    """
    Technician assignment operations.

    Supports assigning technicians to services for:
    - Repair
    - Pick-up (pull-out)
    - Delivery
    - Inspection
    """

    serializer_class = TechnicianAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            TechnicianAssignment.objects.all()
            .select_related(
                "service__client",
                "appliance__appliance_type",
                "technician",
            )
        )

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        """Get filter options for technician assignments."""
        filters_config = {
            "technician": {"options": lambda: get_user_options(include_roles=["technician"])},
            "assignment_type": {
                "options": lambda: [
                    {"label": choice[1], "value": choice[0]}
                    for choice in TechnicianAssignment.AssignmentType.choices
                ]
            },
        }

        ordering_config = [
            {"label": "Service Date", "value": "service__scheduled_date"},
            {"label": "Created At", "value": "id"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)
