"""
Service API views with two-stall architecture support.

Features:
- Service CRUD operations
- Service completion endpoint (consume stock, create transactions)
- Service cancellation endpoint (release reserved stock)
- Revenue calculation and reporting
"""

from django.db.models import Q
from rest_framework import permissions, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from services.api.serializers import (
    ApplianceItemUsedSerializer,
    ApplianceTypeSerializer,
    CreateServicePaymentSerializer,
    ServiceApplianceSerializer,
    ServiceCancellationSerializer,
    ServiceCompletionSerializer,
    ServicePaymentSerializer,
    ServiceRefundRequestSerializer,
    ServiceSerializer,
    TechnicianAssignmentSerializer,
)
from services.api.filters import ServiceFilter
from services.business_logic import RevenueCalculator, ServicePaymentManager
from services.models import (
    ApplianceItemUsed,
    ApplianceType,
    Service,
    ServiceAppliance,
    TechnicianAssignment,
)
from utils.filters.options import (
    get_service_mode_options,
    get_service_payment_status_options,
    get_service_status_options,
    get_service_type_options,
    get_user_options,
)
from utils.filters.role_filters import get_role_based_filter_response
from utils.query import filter_by_date_range, get_role_filtered_queryset


from utils.soft_delete import SoftDeleteViewSetMixin


# --------------------------
# Service ViewSet
# --------------------------
class ServiceViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    """
    Service operations with two-stall architecture support.

    Endpoints:
    - GET /services/ - List services with filters
    - POST /services/ - Create service (reserves stock)
    - GET /services/{id}/ - Retrieve service details
    - PUT/PATCH /services/{id}/ - Update service
    - DELETE /services/{id}/ - Soft-delete (archive) service
    - GET /services/archived/ - List archived services
    - POST /services/{id}/restore/ - Restore archived service
    - DELETE /services/{id}/hard-delete/ - Permanently delete archived service
    - POST /services/{id}/complete/ - Complete service (consume stock, create transactions)
    - POST /services/{id}/cancel/ - Cancel service (release reserved stock)
    - POST /services/{id}/recalculate_revenue/ - Recalculate revenue attribution
    - POST /services/{id}/payments/ - Record a payment for a service
    - GET /services/{id}/payments/ - List all payments for a service
    - GET /services/{id}/payment_summary/ - Get payment summary for a service
    - GET /services/outstanding/ - List services with outstanding balances
    - GET /services/filters/ - Get filter options
    - GET /services/revenue_report/ - Get revenue summary
    """

    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ServiceFilter
    search_fields = [
        "client__full_name",
        "client__contact_number",
        "status",
        "service_type",
        "service_mode",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = (
            Service.objects.all()
            .filter(is_deleted=False)
            .select_related("client", "stall", "related_transaction")
            .prefetch_related(
                "appliances__items_used__item",
                "appliances__items_used__stall_stock__stall",
                "appliances__appliance_type",
                "appliances__assigned_technician",
                "appliances__technician_assignments__technician",
                "technician_assignments__technician",
                "payments",
                "refunds",
                "installation_units__model__brand",
                "schedules",
            )
        )
        
        return filter_by_date_range(self.request, qs)

    def perform_update(self, serializer):
        """Cascade appliance status when service status changes to in_progress."""
        old_status = serializer.instance.status
        service = serializer.save()
        new_status = service.status

        if old_status != new_status and new_status == "in_progress":
            from utils.enums import ApplianceStatus
            # Move appliances that are still in early stages to in_repair
            service.appliances.filter(
                status__in=[ApplianceStatus.RECEIVED, ApplianceStatus.DIAGNOSED]
            ).update(status=ApplianceStatus.IN_REPAIR)
    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """
        Complete a service, consume reserved stock, and create transactions.

        Request body:
        {
            "create_receipt": true,  // Optional: create a receipt
            "notes": "Service completed successfully"  // Optional
        }

        Response:
        {
            "service_id": 123,
            "status": "completed",
            "consumed_items": [
                {"item": "Capacitor", "quantity": 2},
                {"item": "Copper Tube", "quantity": 15}
            ],
            "revenue": {
                "main_revenue": "500.00",
                "sub_revenue": "300.00",
                "total_revenue": "800.00"
            },
            "receipt": 456,          // Primary receipt ID (main or sub)
            "main_receipt": 456,     // Main stall receipt ID (labor + units)
            "sub_receipt": 457       // Sub stall receipt ID (parts)
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

    @action(detail=True, methods=["post"], url_path="refund")
    def refund(self, request, pk=None):
        """
        Process a refund for a completed service.
        Parts are NOT returned to stock (already used).

        Request body:
        {
            "refund_amount": 500.00,
            "reason": "Customer dissatisfaction",
            "refund_type": "partial",  // "full" or "partial"
            "refund_method": "cash"  // "cash", "gcash", or "bank_transfer"
        }

        Response:
        {
            "refund_id": 45,
            "service_id": 123,
            "refund_amount": 500.00,
            "refund_type": "partial",
            "total_refunded": 500.00,
            "net_revenue": 1500.00,
            "parts_returned_to_stock": 0
        }
        """
        service = self.get_object()

        serializer = ServiceRefundRequestSerializer(
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
            "technician": {
                "options": lambda: get_user_options(include_roles=["technician"])
            },
            "status": {"options": get_service_status_options},
            "payment_status": {"options": get_service_payment_status_options},
            "service_type": {"options": get_service_type_options},
            "service_mode": {"options": get_service_mode_options},
        }

        ordering_config = [
            {"label": "Created At (Newest)", "value": "-created_at"},
            {"label": "Created At (Oldest)", "value": "created_at"},
            {"label": "Total Revenue (High to Low)", "value": "-total_revenue"},
            {"label": "Total Revenue (Low to High)", "value": "total_revenue"},
            {"label": "Status", "value": "status"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)

    @action(detail=True, methods=["post"], url_path="payments")
    def create_payment(self, request, pk=None):
        """
        Record a payment for a service.

        Request body:
        {
            "payment_type": "cash",  // Required: cash, gcash, credit, debit, cheque
            "amount": "500.00",      // Required: payment amount
            "notes": "Partial payment"  // Optional
        }

        Response:
        {
            "id": 1,
            "service": 123,
            "payment_type": "cash",
            "payment_type_display": "Cash",
            "amount": "500.00",
            "payment_date": "2024-01-15T10:30:00Z",
            "received_by": 5,
            "received_by_name": "John Doe",
            "notes": "Partial payment",
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:30:00Z"
        }
        """
        service = self.get_object()

        serializer = CreateServicePaymentSerializer(
            data=request.data,
            context={"service": service, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()

        # Return the created payment
        output_serializer = ServicePaymentSerializer(payment)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="payments")
    def list_payments(self, request, pk=None):
        """
        List all payments for a service.

        Response:
        [
            {
                "id": 1,
                "service": 123,
                "payment_type": "cash",
                "amount": "500.00",
                ...
            },
            ...
        ]
        """
        service = self.get_object()
        payments = service.payments.all()
        serializer = ServicePaymentSerializer(payments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="payment-summary")
    def payment_summary(self, request, pk=None):
        """
        Get payment summary for a service.

        Response:
        {
            "service_id": 123,
            "total_revenue": "1000.00",
            "total_paid": "500.00",
            "balance_due": "500.00",
            "payment_status": "partial",
            "payments": [...]
        }
        """
        service = self.get_object()
        summary = ServicePaymentManager.get_payment_summary(service)
        return Response(summary, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="schedule-delivery")
    def schedule_delivery(self, request, pk=None):
        """
        Schedule delivery for a pull-out service.

        Creates a delivery Schedule when the appliance is ready.

        Request body:
        {
            "delivery_date": "2024-02-01",  // Required: date for delivery
            "delivery_time": "14:00:00",     // Optional: time for delivery (default 14:00)
            "notes": "Ready for delivery"    // Optional: additional notes
        }

        Response:
        {
            "service_id": 123,
            "delivery_date": "2024-02-01",
            "schedule_id": 456,
            "message": "Delivery scheduled successfully"
        }
        """
        from datetime import datetime
        from datetime import time as dt_time

        from schedules.models import Schedule
        from utils.enums import ServiceMode

        service = self.get_object()

        # Validate service is pull-out
        if service.service_mode != ServiceMode.PULL_OUT:
            return Response(
                {"error": "Only pull-out services can schedule delivery"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get delivery date from request
        delivery_date_str = request.data.get('delivery_date')
        if not delivery_date_str:
            return Response(
                {"error": "delivery_date is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get delivery time (default to 2 PM)
        delivery_time_str = request.data.get('delivery_time', '14:00:00')
        try:
            delivery_time = datetime.strptime(delivery_time_str, '%H:%M:%S').time()
        except ValueError:
            delivery_time = dt_time(14, 0)

        # Update service delivery_date
        service.delivery_date = delivery_date
        service.save(update_fields=['delivery_date'])

        # Get technicians from service
        technician_ids = service.technician_assignments.filter(
            assignment_type='repair'
        ).values_list('technician_id', flat=True)

        # Create delivery schedule
        schedule = Schedule.objects.create(
            client=service.client,
            service=service,
            schedule_type='return',
            scheduled_date=delivery_date,
            scheduled_time=delivery_time,
            estimated_duration=60,
            status='pending',
            address=service.override_address or service.client.address,
            contact_person=service.override_contact_person or service.client.full_name,
            contact_number=service.override_contact_number or service.client.contact_number,
            notes=request.data.get('notes', f"Delivery for {service.description}"),
            created_by=request.user if hasattr(request, 'user') else None
        )

        # Assign technicians to delivery schedule
        if technician_ids:
            from users.models import CustomUser
            technicians = CustomUser.objects.filter(id__in=technician_ids)
            schedule.technicians.set(technicians)

        return Response(
            {
                "service_id": service.id,
                "delivery_date": str(delivery_date),
                "schedule_id": schedule.id,
                "message": "Delivery scheduled successfully"
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["get"], url_path="outstanding")
    def outstanding(self, request):
        """
        List services with outstanding balances (unpaid or partial).

        Query params:
        - stall: Filter by stall ID (optional)
        - start_date: Filter services from this date (YYYY-MM-DD)
        - end_date: Filter services to this date (YYYY-MM-DD)

        Response:
        [
            {
                "id": 123,
                "client": {...},
                "total_revenue": "1000.00",
                "total_paid": "500.00",
                "balance_due": "500.00",
                "payment_status": "partial",
                ...
            },
            ...
        ]
        """
        from inventory.models import Stall

        # Get outstanding services
        stall_id = request.query_params.get("stall")
        stall = None
        if stall_id:
            try:
                stall = Stall.objects.get(id=stall_id)
            except Stall.DoesNotExist:
                return Response(
                    {"error": f"Stall with ID {stall_id} not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

        qs = ServicePaymentManager.get_outstanding_services(stall=stall)

        # Apply date filters
        qs = filter_by_date_range(request, qs)

        # Serialize
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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

    def perform_create(self, serializer):
        """Create appliance and recalculate service revenue."""
        appliance = serializer.save()
        # Recalculate revenue after creating appliance
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        RevenueCalculator.calculate_service_revenue(appliance.service, save=True)
        # Sync sales items if transaction exists
        ServicePaymentManager.sync_sales_items(appliance.service)

    def perform_update(self, serializer):
        """Update appliance and recalculate service revenue."""
        appliance = serializer.save()
        # Recalculate revenue after updating appliance
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        RevenueCalculator.calculate_service_revenue(appliance.service, save=True)
        # Sync sales items if transaction exists
        ServicePaymentManager.sync_sales_items(appliance.service)

    def perform_destroy(self, instance):
        """Delete appliance and recalculate service revenue."""
        service = instance.service
        instance.delete()
        # Recalculate revenue after deleting appliance
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        RevenueCalculator.calculate_service_revenue(service, save=True)
        # Sync sales items if transaction exists
        ServicePaymentManager.sync_sales_items(service)


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
        queryset = (
            ApplianceItemUsed.objects.all()
            .select_related(
                "appliance__service",
                "appliance__appliance_type",
                "item",
                "stall_stock__stall",
                "expense",
            )
        )
        
        # Filter by appliance if provided
        appliance_id = self.request.query_params.get('appliance')
        if appliance_id:
            queryset = queryset.filter(appliance_id=appliance_id)
        
        return queryset

    def perform_create(self, serializer):
        """Create item usage and recalculate service revenue."""
        item_used = serializer.save()
        # Recalculate revenue after adding parts
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        service = item_used.appliance.service
        RevenueCalculator.calculate_service_revenue(service, save=True)
        # Sync sales items if transaction exists
        ServicePaymentManager.sync_sales_items(service)

    def perform_update(self, serializer):
        """Update item usage and recalculate service revenue."""
        item_used = serializer.save()
        # Recalculate revenue after updating parts
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        service = item_used.appliance.service
        RevenueCalculator.calculate_service_revenue(service, save=True)
        # Sync sales items if transaction exists
        ServicePaymentManager.sync_sales_items(service)

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

        # Store service reference before deletion
        service = instance.appliance.service
        
        result = super().destroy(request, *args, **kwargs)
        
        # Recalculate revenue and sync sales items after deletion
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        RevenueCalculator.calculate_service_revenue(service, save=True)
        ServicePaymentManager.sync_sales_items(service)
        
        return result


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


# --------------------------
# ApplianceType ViewSet
# --------------------------
class ApplianceTypeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing appliance types.

    Endpoints:
    - GET /appliance-types/ - List all appliance types
    - POST /appliance-types/ - Create a new appliance type
    - GET /appliance-types/{id}/ - Retrieve an appliance type
    - PATCH /appliance-types/{id}/ - Update an appliance type
    - DELETE /appliance-types/{id}/ - Delete an appliance type
    """

    queryset = ApplianceType.objects.all()
    serializer_class = ApplianceTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["name"]
    search_fields = ["name"]
    ordering_fields = ["name", "id"]
    ordering = ["name"]
