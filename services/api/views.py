"""
Service API views with two-stall architecture support.

Features:
- Service CRUD operations
- Service completion endpoint (consume stock, create transactions)
- Service cancellation endpoint (release reserved stock)
- Revenue calculation and reporting
"""

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from services.api.serializers import (
    ApplianceItemUsedSerializer,
    ApplianceTypeSerializer,
    CompanyAssetSerializer,
    ServiceItemUsedSerializer,
    CreateServicePaymentSerializer,
    JobOrderTemplatePrintSerializer,
    ServiceApplianceSerializer,
    ServiceCancellationSerializer,
    ServiceCompletionSerializer,
    ServicePaymentSerializer,
    ServiceReceiptSerializer,
    ServiceRefundRequestSerializer,
    ServiceReopenSerializer,
    ServiceSerializer,
    TechnicianAssignmentSerializer,
)
from services.api.filters import ServiceFilter
from services.business_logic import RevenueCalculator, ServicePaymentManager
from services.models import (
    ApplianceItemUsed,
    ApplianceType,
    CompanyAsset,
    JobOrderTemplatePrint,
    Service,
    ServiceAppliance,
    ServiceItemUsed,
    ServiceReceipt,
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
from utils.permissions import IsAdminOrManager
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
    allow_hard_delete = True
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    def get_permissions(self):
        if self.action in ("create", "hard_delete"):
            return [IsAdminOrManager()]
        return super().get_permissions()
    filterset_class = ServiceFilter
    search_fields = [
        "client__full_name",
        "client__contact_number",
        "status",
        "service_type",
        "service_mode",
        "appliances__appliance_type__name",
        "appliances__brand",
        "appliances__model",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = (
            Service.objects.all()
            .filter(is_deleted=False)
            .select_related("client", "stall", "related_transaction", "service_items_checked_by", "back_job_parent")
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
            .distinct()
        )

        return filter_by_date_range(self.request, qs)

    def perform_update(self, serializer):
        """Cascade appliance status and auto-reset service items_checked if notes changed."""
        old_status = serializer.instance.status
        old_notes = serializer.instance.service_parts_needed_notes or ""
        old_discount = serializer.instance.service_discount_amount or 0
        service = serializer.save()
        new_status = service.status
        new_notes = service.service_parts_needed_notes or ""
        new_discount = service.service_discount_amount or 0

        # Track discount audit info
        if new_discount != old_discount:
            if new_discount > 0:
                service.discount_applied_by = self.request.user
                service.discount_applied_at = timezone.now()
            else:
                service.discount_applied_by = None
                service.discount_applied_at = None
            service.save(
                update_fields=["discount_applied_by", "discount_applied_at"],
                skip_validation=True,
            )

        if old_status != new_status and new_status == "in_progress":
            pass  # Appliance statuses are simplified (pending/completed/cancelled), no cascade needed

        # Auto-reset service_items_checked if service_parts_needed_notes changed
        if old_notes != new_notes and service.service_items_checked:
            service.service_items_checked = False
            service.service_items_checked_by = None
            service.service_items_checked_at = None
            service.save(
                update_fields=["service_items_checked", "service_items_checked_by", "service_items_checked_at"],
                skip_validation=True,
            )

    @action(detail=True, methods=["post"], url_path="complete", permission_classes=[IsAdminOrManager])
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

    @action(detail=True, methods=["post"], url_path="cancel", permission_classes=[IsAdminOrManager])
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

    @action(detail=True, methods=["post"], url_path="reopen", permission_classes=[IsAdminOrManager])
    def reopen(self, request, pk=None):
        """
        Reopen a completed service for revision.

        Reverses completion side effects (voids transactions, returns stock,
        resets warranties) while preserving customer payments.

        Request body:
        {
            "reason": "Need to add parts"  // Optional
        }
        """
        service = self.get_object()

        serializer = ServiceReopenSerializer(
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

    @action(
        detail=True,
        methods=["post"],
        url_path="link-aircon-units",
        permission_classes=[IsAdminOrManager],
    )
    def link_aircon_units(self, request, pk=None):
        """
        Link aircon units to an existing service, claiming free cleaning and/or
        filing warranty claims as appropriate.

        Request body:
        {
            "free_cleaning_unit_ids": [1, 2],
            "warranty_unit_ids": [
                {"unit_id": 3, "claim_type": "repair", "issue_description": "Not cooling"}
            ]
        }
        """
        from installations.models import AirconUnit
        from installations.business_logic import FreeCleaningManager, WarrantyClaimManager
        from services.models import ServiceAppliance

        service = self.get_object()

        free_cleaning_unit_ids = request.data.get("free_cleaning_unit_ids", [])
        warranty_unit_ids = request.data.get("warranty_unit_ids", [])
        warranty_appliance_ids = request.data.get("warranty_appliance_ids", [])

        results = {"free_cleaning": [], "warranty_claims": [], "warranty_appliances": [], "errors": []}

        # --- Free cleaning units ---
        for unit_id in free_cleaning_unit_ids:
            try:
                unit = AirconUnit.objects.get(id=unit_id)
                eligibility = FreeCleaningManager.check_eligibility(unit)
                if not eligibility["eligible"]:
                    results["errors"].append(
                        {"unit_id": unit_id, "error": eligibility["reason"]}
                    )
                    continue
                unit.free_cleaning_redeemed = True
                unit.free_cleaning_service = service
                unit.save(clean=False)
                results["free_cleaning"].append(unit_id)
            except AirconUnit.DoesNotExist:
                results["errors"].append({"unit_id": unit_id, "error": "Unit not found"})

        # --- Warranty claim units ---
        for entry in warranty_unit_ids:
            unit_id = entry.get("unit_id")
            claim_type = entry.get("claim_type", "repair")
            issue_description = entry.get("issue_description", "Warranty service")
            try:
                unit = AirconUnit.objects.get(id=unit_id)
                claim = WarrantyClaimManager.create_claim(
                    unit=unit,
                    issue_description=issue_description,
                    claim_type=claim_type,
                    customer_notes=entry.get("customer_notes", ""),
                )
                # Note: service FK is OneToOneField; leave it null here so
                # the normal approval flow can assign/create a service later.
                results["warranty_claims"].append(claim.id)
                # Clone unit info as an appliance in the warranty service
                brand_name = unit.model.brand.name if unit.model and unit.model.brand else ""
                model_name = unit.model.name if unit.model else ""
                ServiceAppliance.objects.create(
                    service=service,
                    brand=brand_name,
                    model=model_name,
                    serial_number=unit.serial_number or "",
                    issue_reported=issue_description,
                    status="received",
                    labor_is_free=True,
                    labor_fee=0,
                    labor_warranty_months=0,
                    unit_warranty_months=0,
                )
            except AirconUnit.DoesNotExist:
                results["errors"].append({"unit_id": unit_id, "error": "Unit not found"})
            except Exception as exc:
                results["errors"].append({"unit_id": unit_id, "error": str(exc)})

        # --- Warranty appliances (from past repairs) ---
        for appliance_id in warranty_appliance_ids:
            try:
                original = ServiceAppliance.objects.get(id=appliance_id)
                # Clone the appliance into the new warranty claim service
                ServiceAppliance.objects.create(
                    service=service,
                    appliance_type=original.appliance_type,
                    brand=original.brand,
                    model=original.model,
                    serial_number=original.serial_number,
                    issue_reported=f"Warranty claim (original service #{original.service_id})",
                    status="received",
                    labor_is_free=True,
                    labor_fee=0,
                    labor_warranty_months=0,
                    unit_warranty_months=0,
                )
                results["warranty_appliances"].append(appliance_id)
            except ServiceAppliance.DoesNotExist:
                results["errors"].append({"appliance_id": appliance_id, "error": "Appliance not found"})

        # Mark service as complementary if any units linked
        if results["free_cleaning"] or results["warranty_claims"] or results["warranty_appliances"]:
            if not service.is_complementary:
                reasons = []
                if results["free_cleaning"]:
                    reasons.append("Free Cleaning")
                if results["warranty_claims"]:
                    reasons.append("Warranty")
                service.is_complementary = True
                service.complementary_reason = ", ".join(reasons)
                service.save(update_fields=["is_complementary", "complementary_reason"])

        return Response(results, status=status.HTTP_200_OK)

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
            "has_receipt": {
                "options": lambda: [
                    {"label": "With Receipt", "value": "with"},
                    {"label": "Without Receipt", "value": "without"},
                ]
            },
            "receipt_type": {
                "options": lambda: [
                    {"label": "Official Receipt (OR)", "value": "or"},
                    {"label": "Sales Invoice (SI)", "value": "si"},
                ]
            },
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

    @action(detail=True, methods=["post"], url_path="mark-claimed", permission_classes=[IsAdminOrManager])
    def mark_claimed(self, request, pk=None):
        """
        Record that the client has picked up the repaired appliance (carry-in)
        or that RVDC has delivered it back (pull-out).
        Stops the 2-month unclaimed clock.
        """
        from django.utils import timezone as tz
        from utils.enums import ServiceMode

        service = self.get_object()
        if service.service_mode == ServiceMode.HOME_SERVICE:
            return Response(
                {"detail": "Home-service jobs do not have a claim/delivery step."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if service.claimed_at:
            return Response(
                {"detail": "Already marked as claimed.", "claimed_at": service.claimed_at},
                status=status.HTTP_200_OK,
            )
        service.claimed_at = request.data.get("claimed_at") or tz.now()
        service.save(update_fields=["claimed_at"])
        return Response(
            {"detail": "Marked as claimed.", "claimed_at": service.claimed_at},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="mark-forfeited", permission_classes=[IsAdminOrManager])
    def mark_forfeited(self, request, pk=None):
        """
        Declare the appliance as company property (2-month unclaimed policy or admin decision).
        Sets payment_status to WRITTEN_OFF and creates a CompanyAsset record.
        """
        from django.utils import timezone as tz
        from services.models import PaymentStatus

        service = self.get_object()
        if service.is_forfeited:
            return Response({"detail": "Already forfeited."}, status=status.HTTP_200_OK)
        if service.claimed_at:
            return Response(
                {"detail": "Cannot forfeit a service that has already been claimed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notes = request.data.get("forfeiture_notes", "")
        service.is_forfeited = True
        service.forfeited_at = tz.now()
        service.forfeiture_type = Service.ForfeitureType.UNCLAIMED
        service.forfeiture_notes = notes
        service.payment_status = PaymentStatus.WRITTEN_OFF
        service.save(update_fields=[
            "is_forfeited", "forfeited_at", "forfeiture_type",
            "forfeiture_notes", "payment_status",
        ])

        # Build a description of all appliances
        appliance_descriptions = "; ".join(
            str(a) for a in service.appliances.select_related("appliance_type").all()
        ) or "Unspecified appliance"

        asset = CompanyAsset.objects.create(
            service=service,
            appliance_description=appliance_descriptions,
            acquisition_type=CompanyAsset.AcquisitionType.UNCLAIMED,
            acquired_by=request.user,
            condition_notes=notes,
        )
        return Response(
            {
                "detail": "Service forfeited. Appliance recorded as company asset.",
                "asset_id": asset.id,
                "payment_status": service.payment_status,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="convert-to-acquisition", permission_classes=[IsAdminOrManager])
    def convert_to_acquisition(self, request, pk=None):
        """
        Client agrees to sell their appliance to the company instead of paying
        or collecting after repair. Cancels any remaining balance and records
        a CompanyAsset at the agreed acquisition_price.
        """
        from django.utils import timezone as tz
        from services.models import PaymentStatus

        service = self.get_object()
        if service.is_forfeited:
            return Response({"detail": "Already forfeited/acquired."}, status=status.HTTP_400_BAD_REQUEST)

        acquisition_price = request.data.get("acquisition_price")
        notes = request.data.get("notes", "")
        try:
            acquisition_price = float(acquisition_price) if acquisition_price is not None else None
        except (ValueError, TypeError):
            return Response({"detail": "acquisition_price must be a number."}, status=status.HTTP_400_BAD_REQUEST)

        service.is_forfeited = True
        service.forfeited_at = tz.now()
        service.forfeiture_type = Service.ForfeitureType.CLIENT_SOLD
        service.forfeiture_notes = notes
        service.acquisition_price = acquisition_price
        service.payment_status = PaymentStatus.WRITTEN_OFF
        service.save(update_fields=[
            "is_forfeited", "forfeited_at", "forfeiture_type",
            "forfeiture_notes", "acquisition_price", "payment_status",
        ])

        appliance_descriptions = "; ".join(
            str(a) for a in service.appliances.select_related("appliance_type").all()
        ) or "Unspecified appliance"

        asset = CompanyAsset.objects.create(
            service=service,
            appliance_description=appliance_descriptions,
            acquisition_type=CompanyAsset.AcquisitionType.CLIENT_SOLD,
            acquisition_price=acquisition_price,
            acquired_by=request.user,
            condition_notes=notes,
        )
        return Response(
            {
                "detail": "Converted to company acquisition.",
                "asset_id": asset.id,
                "payment_status": service.payment_status,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="unclaimed-eligible", permission_classes=[IsAdminOrManager])
    def unclaimed_eligible(self, request):
        """
        List carry-in and pull-out services that have been completed for ≥60 days
        without being claimed. Used for the forfeiture alert dashboard.
        """
        from datetime import timedelta
        from django.utils import timezone as tz
        from utils.enums import ServiceMode

        sixty_days_ago = tz.now() - timedelta(days=60)
        qs = (
            Service.objects.filter(
                is_deleted=False,
                status="completed",
                service_mode__in=[ServiceMode.CARRY_IN, ServiceMode.PULL_OUT],
                claimed_at__isnull=True,
                is_forfeited=False,
                completed_at__lte=sixty_days_ago,
            )
            .select_related("client", "stall")
            .prefetch_related("appliances__appliance_type")
            .order_by("completed_at")
        )
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

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

    @action(detail=False, methods=["get"], url_path="pending-items-stats")
    def pending_items_stats(self, request):
        """
        Get stats on services with pending item reviews (unchecked appliances).
        Used for the clerk dashboard widget and service overview.
        """
        from django.db.models import Count, F

        # Active services (not completed/cancelled) with unchecked appliances
        active_services = Service.objects.filter(
            is_deleted=False,
            status__in=["pending", "in_progress", "on_hold"],
        ).prefetch_related("appliances", "client")

        pending_services = []
        for service in active_services:
            # Only count appliances where manager has noted parts are needed
            unchecked = service.appliances.filter(
                items_checked=False,
            ).exclude(parts_needed_notes="")
            has_service_pending = (
                bool(service.service_parts_needed_notes)
                and not service.service_items_checked
            )
            if unchecked.exists() or has_service_pending:
                pending_services.append({
                    "service_id": service.id,
                    "client_name": service.client.full_name if service.client else "Unknown",
                    "service_type": service.service_type,
                    "status": service.status,
                    "created_at": service.created_at,
                    "total_appliances": service.appliances.count(),
                    "unchecked_appliances": unchecked.count(),
                    "has_service_level_pending": has_service_pending,
                    "appliances": [
                        {
                            "id": a.id,
                            "name": str(a),
                            "parts_needed_notes": a.parts_needed_notes,
                            "items_count": a.items_used.count(),
                        }
                        for a in unchecked
                    ],
                })

        total_unchecked = sum(s["unchecked_appliances"] for s in pending_services)
        total_service_level = sum(1 for s in pending_services if s["has_service_level_pending"])

        return Response({
            "total_pending_services": len(pending_services),
            "total_unchecked_appliances": total_unchecked,
            "total_service_level_pending": total_service_level,
            "total_pending_items": total_unchecked + total_service_level,
            "services": pending_services,
        })

    @action(detail=True, methods=["post"], url_path="toggle-service-items-checked")
    def toggle_service_items_checked(self, request, pk=None):
        """Toggle service-level items_checked status. Only clerk and admin can confirm."""
        from django.utils import timezone

        if request.user.role not in ("clerk", "admin"):
            return Response(
                {"detail": "Only clerks and admins can confirm items."},
                status=403,
            )

        service = self.get_object()
        new_value = not service.service_items_checked

        if new_value:
            # Block confirming when parts are needed but no service items have been added
            if service.service_parts_needed_notes and service.service_items.count() == 0:
                return Response(
                    {"detail": "Cannot confirm items — parts are listed as needed but no items have been added yet."},
                    status=400,
                )
            service.service_items_checked = True
            service.service_items_checked_by = request.user
            service.service_items_checked_at = timezone.now()
        else:
            service.service_items_checked = False
            service.service_items_checked_by = None
            service.service_items_checked_at = None

        service.save(
            update_fields=[
                "service_items_checked",
                "service_items_checked_by",
                "service_items_checked_at",
            ],
            skip_validation=True,
        )

        return Response({
            "id": service.id,
            "service_items_checked": service.service_items_checked,
            "service_items_checked_by": service.service_items_checked_by_id,
            "service_items_checked_at": service.service_items_checked_at,
        })


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
        from django.utils import timezone
        from django.db.models import Q

        qs = (
            ServiceAppliance.objects.all()
            .select_related("service", "appliance_type")
            .prefetch_related(
                "items_used__item",
                "items_used__stall_stock__stall",
                "technician_assignments__technician",
            )
        )

        client_id = self.request.query_params.get("client")
        if client_id:
            qs = qs.filter(service__client_id=client_id)

        # ?warranty_active=true  →  only appliances with at least one active warranty
        if self.request.query_params.get("warranty_active") == "true":
            today = timezone.now().date()
            qs = qs.filter(
                Q(labor_warranty_end_date__gte=today) |
                Q(unit_warranty_end_date__gte=today)
            ).filter(warranty_start_date__lte=today)

        return qs

    def perform_create(self, serializer):
        """Create appliance, recalculate revenue, and notify clerks."""
        appliance = serializer.save()
        # Recalculate revenue after creating appliance
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        RevenueCalculator.calculate_service_revenue(appliance.service, save=True)
        # Sync sales items if transaction exists
        ServicePaymentManager.sync_sales_items(appliance.service)
        # Notify clerks about new appliance needing items review
        self._notify_clerks_items_pending(appliance)

    def perform_update(self, serializer):
        """Update appliance and recalculate service revenue. Auto-reset items_checked if parts_needed_notes changed."""
        old_notes = serializer.instance.parts_needed_notes or ""
        appliance = serializer.save()
        new_notes = appliance.parts_needed_notes or ""
        # Recalculate revenue after updating appliance
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        RevenueCalculator.calculate_service_revenue(appliance.service, save=True)
        # Sync sales items if transaction exists
        ServicePaymentManager.sync_sales_items(appliance.service)
        # Auto-reset items_checked if parts_needed_notes changed and was already confirmed
        if old_notes != new_notes and appliance.items_checked:
            appliance.items_checked = False
            appliance.items_checked_by = None
            appliance.items_checked_at = None
            appliance.save(update_fields=["items_checked", "items_checked_by", "items_checked_at"])
            # Re-notify clerks
            if new_notes:
                self._notify_clerks_items_pending(appliance)

    def perform_destroy(self, instance):
        """Delete appliance and recalculate service revenue."""
        service = instance.service
        instance.delete()
        # Recalculate revenue after deleting appliance
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        RevenueCalculator.calculate_service_revenue(service, save=True)
        # Sync sales items if transaction exists
        ServicePaymentManager.sync_sales_items(service)

    @action(detail=True, methods=["post"], url_path="toggle-items-checked")
    def toggle_items_checked(self, request, pk=None):
        """Toggle items_checked status for an appliance. Only clerk and admin can confirm."""
        from django.utils import timezone

        if request.user.role not in ("clerk", "admin"):
            return Response(
                {"detail": "Only clerks and admins can confirm items."},
                status=403,
            )

        appliance = self.get_object()
        new_value = not appliance.items_checked

        if new_value:
            # Block confirming when parts are needed but no items have been added
            if appliance.parts_needed_notes and appliance.items_used.count() == 0:
                return Response(
                    {"detail": "Cannot confirm items — parts are listed as needed but no items have been added yet."},
                    status=400,
                )
            appliance.items_checked = True
            appliance.items_checked_by = request.user
            appliance.items_checked_at = timezone.now()
        else:
            appliance.items_checked = False
            appliance.items_checked_by = None
            appliance.items_checked_at = None

        appliance.save(update_fields=[
            "items_checked", "items_checked_by", "items_checked_at"
        ])

        return Response({
            "id": appliance.id,
            "items_checked": appliance.items_checked,
            "items_checked_by": appliance.items_checked_by_id,
            "items_checked_at": appliance.items_checked_at,
        })

    @action(detail=True, methods=["post"], url_path="mark-claimed", permission_classes=[IsAdminOrManager])
    def mark_claimed(self, request, pk=None):
        """
        Record that the client has collected this specific appliance.
        Updates the service-level claimed_at when all appliances are claimed.
        """
        from django.utils import timezone as tz
        from utils.enums import ServiceMode

        appliance = self.get_object()
        service = appliance.service

        if service.service_mode == ServiceMode.HOME_SERVICE:
            return Response(
                {"detail": "Home-service jobs do not have a claim/delivery step."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if appliance.claimed_at:
            return Response(
                {"detail": "Already marked as claimed.", "claimed_at": appliance.claimed_at},
                status=status.HTTP_200_OK,
            )
        if appliance.is_forfeited:
            return Response(
                {"detail": "This appliance has already been forfeited/acquired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        appliance.claimed_at = request.data.get("claimed_at") or tz.now()
        appliance.save(update_fields=["claimed_at"])

        # Update service-level claimed_at if every appliance is now claimed
        all_appliances = list(service.appliances.all())
        if all(a.claimed_at for a in all_appliances):
            service.claimed_at = tz.now()
            service.save(update_fields=["claimed_at"])

        return Response(
            {"detail": "Appliance marked as claimed.", "claimed_at": appliance.claimed_at},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="mark-forfeited", permission_classes=[IsAdminOrManager])
    def mark_forfeited(self, request, pk=None):
        """
        Declare this specific appliance as company property (2-month unclaimed policy).
        Creates an individual CompanyAsset record for this appliance.
        """
        from django.utils import timezone as tz
        from services.models import PaymentStatus, CompanyAsset

        appliance = self.get_object()
        service = appliance.service

        if appliance.is_forfeited:
            return Response({"detail": "Already forfeited."}, status=status.HTTP_200_OK)
        if appliance.claimed_at:
            return Response(
                {"detail": "Cannot forfeit an appliance that has already been claimed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notes = request.data.get("forfeiture_notes", "")
        appliance.is_forfeited = True
        appliance.forfeiture_type = "unclaimed"
        appliance.forfeiture_notes = notes
        appliance.save(update_fields=["is_forfeited", "forfeiture_type", "forfeiture_notes"])

        asset = CompanyAsset.objects.create(
            service=service,
            service_appliance=appliance,
            appliance_description=str(appliance),
            acquisition_type=CompanyAsset.AcquisitionType.UNCLAIMED,
            acquired_by=request.user,
            condition_notes=notes,
        )

        # Update service-level if every appliance is now either claimed or forfeited
        all_appliances = list(service.appliances.all())
        all_resolved = all(a.claimed_at or a.is_forfeited for a in all_appliances)
        any_forfeited = any(a.is_forfeited for a in all_appliances)
        if all_resolved and any_forfeited and not service.is_forfeited:
            service.is_forfeited = True
            service.forfeited_at = tz.now()
            service.forfeiture_type = Service.ForfeitureType.UNCLAIMED
            service.forfeiture_notes = notes
            service.payment_status = PaymentStatus.WRITTEN_OFF
            service.save(update_fields=[
                "is_forfeited", "forfeited_at", "forfeiture_type",
                "forfeiture_notes", "payment_status",
            ])

        return Response(
            {
                "detail": "Appliance forfeited and recorded as company asset.",
                "asset_id": asset.id,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="convert-to-acquisition", permission_classes=[IsAdminOrManager])
    def convert_to_acquisition(self, request, pk=None):
        """
        Client agrees to sell this specific appliance to the company.
        Creates an individual CompanyAsset record at the agreed acquisition_price.
        """
        from django.utils import timezone as tz
        from services.models import PaymentStatus, CompanyAsset

        appliance = self.get_object()
        service = appliance.service

        if appliance.is_forfeited:
            return Response({"detail": "Already forfeited/acquired."}, status=status.HTTP_400_BAD_REQUEST)
        if appliance.claimed_at:
            return Response(
                {"detail": "Cannot acquire an appliance that has already been claimed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        acquisition_price = request.data.get("acquisition_price")
        notes = request.data.get("notes", "")
        try:
            acquisition_price = float(acquisition_price) if acquisition_price is not None else None
        except (ValueError, TypeError):
            return Response({"detail": "acquisition_price must be a number."}, status=status.HTTP_400_BAD_REQUEST)

        appliance.is_forfeited = True
        appliance.forfeiture_type = "client_sold"
        appliance.forfeiture_notes = notes
        appliance.acquisition_price = acquisition_price
        appliance.save(update_fields=["is_forfeited", "forfeiture_type", "forfeiture_notes", "acquisition_price"])

        asset = CompanyAsset.objects.create(
            service=service,
            service_appliance=appliance,
            appliance_description=str(appliance),
            acquisition_type=CompanyAsset.AcquisitionType.CLIENT_SOLD,
            acquisition_price=acquisition_price,
            acquired_by=request.user,
            condition_notes=notes,
        )

        # Update service-level if every appliance is now either claimed or forfeited
        all_appliances = list(service.appliances.all())
        all_resolved = all(a.claimed_at or a.is_forfeited for a in all_appliances)
        any_forfeited = any(a.is_forfeited for a in all_appliances)
        if all_resolved and any_forfeited and not service.is_forfeited:
            service.is_forfeited = True
            service.forfeited_at = tz.now()
            service.forfeiture_type = Service.ForfeitureType.CLIENT_SOLD
            service.forfeiture_notes = notes
            service.acquisition_price = acquisition_price
            service.payment_status = PaymentStatus.WRITTEN_OFF
            service.save(update_fields=[
                "is_forfeited", "forfeited_at", "forfeiture_type",
                "forfeiture_notes", "acquisition_price", "payment_status",
            ])

        return Response(
            {
                "detail": "Appliance converted to company acquisition.",
                "asset_id": asset.id,
            },
            status=status.HTTP_200_OK,
        )

    def _notify_clerks_items_pending(self, appliance):
        """Send notification to clerks about appliance needing item review."""
        try:
            from accounts.models import CustomUser
            from notifications.models import Notification, NotificationType

            service = appliance.service
            clerks = CustomUser.objects.filter(role="clerk", is_active=True)
            notes_preview = f" — Notes: {appliance.parts_needed_notes[:80]}" if appliance.parts_needed_notes else ""
            Notification.objects.bulk_create([
                Notification(
                    user=clerk,
                    type=NotificationType.ITEMS_PENDING_REVIEW,
                    title=f"Items pending: Service #{service.id}",
                    message=(
                        f"New appliance '{appliance}' added to Service #{service.id} "
                        f"({service.client.full_name if service.client else 'Unknown'}).{notes_preview} "
                        f"Please review and add parts used."
                    ),
                    data={
                        "service_id": service.id,
                        "appliance_id": appliance.id,
                    },
                )
                for clerk in clerks
            ])
        except Exception:
            pass  # Don't fail appliance creation if notification fails


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
    pagination_class = None

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
        """Create item usage, recalculate revenue, and reset items_checked."""
        item_used = serializer.save()
        # Recalculate revenue after adding parts
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        service = item_used.appliance.service
        RevenueCalculator.calculate_service_revenue(service, save=True)
        # Sync sales items if transaction exists
        ServicePaymentManager.sync_sales_items(service)
        # Auto-reset items_checked on the appliance
        self._reset_items_checked(item_used.appliance)

    def perform_update(self, serializer):
        """Update item usage, recalculate revenue, and reset items_checked."""
        item_used = serializer.save()
        # Recalculate revenue after updating parts
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        service = item_used.appliance.service
        RevenueCalculator.calculate_service_revenue(service, save=True)
        # Sync sales items if transaction exists
        ServicePaymentManager.sync_sales_items(service)
        # Auto-reset items_checked on the appliance
        self._reset_items_checked(item_used.appliance)

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

        # Cancel any pending stock requests for this item
        from inventory.models import StockRequest
        StockRequest.objects.filter(
            appliance_item=instance, status='pending'
        ).update(status='cancelled')

        # Store service and appliance reference before deletion
        service = instance.appliance.service
        appliance = instance.appliance

        result = super().destroy(request, *args, **kwargs)

        # Recalculate revenue and sync sales items after deletion
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        RevenueCalculator.calculate_service_revenue(service, save=True)
        ServicePaymentManager.sync_sales_items(service)
        # Auto-reset items_checked on the appliance
        self._reset_items_checked(appliance)

        return result

    def _reset_items_checked(self, appliance):
        """Reset items_checked if it was confirmed, and re-notify clerks."""
        if appliance.items_checked:
            appliance.items_checked = False
            appliance.items_checked_by = None
            appliance.items_checked_at = None
            appliance.save(update_fields=["items_checked", "items_checked_by", "items_checked_at"])
            # Re-notify clerks if parts_needed_notes is present
            if appliance.parts_needed_notes:
                try:
                    from accounts.models import CustomUser
                    from notifications.models import Notification, NotificationType

                    service = appliance.service
                    clerks = CustomUser.objects.filter(role="clerk", is_active=True)
                    Notification.objects.bulk_create([
                        Notification(
                            user=clerk,
                            type=NotificationType.ITEMS_PENDING_REVIEW,
                            title="Items need re-review",
                            message=(
                                f"Parts were changed on {appliance} in service #{service.id} "
                                f"({service.client}). Please re-confirm items."
                            ),
                            data={"service_id": service.id, "appliance_id": appliance.id},
                        )
                        for clerk in clerks
                    ])
                except Exception:
                    pass


# --------------------------
# Service-Level Items ViewSet
# --------------------------
class ServiceItemUsedViewSet(viewsets.ModelViewSet):
    """
    Service-level items used operations.

    For parts used at the service level (not tied to any appliance),
    e.g. chipping work before the AC unit arrives.
    """

    serializer_class = ServiceItemUsedSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        queryset = (
            ServiceItemUsed.objects.all()
            .select_related(
                "service",
                "item",
                "stall_stock__stall",
                "expense",
            )
        )

        service_id = self.request.query_params.get('service')
        if service_id:
            queryset = queryset.filter(service_id=service_id)

        return queryset

    def perform_create(self, serializer):
        item_used = serializer.save()
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        service = item_used.service
        RevenueCalculator.calculate_service_revenue(service, save=True)
        ServicePaymentManager.sync_sales_items(service)
        self._reset_service_items_checked(service)

    def perform_update(self, serializer):
        item_used = serializer.save()
        from services.business_logic import RevenueCalculator, ServicePaymentManager
        service = item_used.service
        RevenueCalculator.calculate_service_revenue(service, save=True)
        ServicePaymentManager.sync_sales_items(service)
        self._reset_service_items_checked(service)

    def destroy(self, request, *args, **kwargs):
        from services.business_logic import StockReservationManager

        instance = self.get_object()

        # Block deletion on completed services
        from utils.enums import ServiceStatus
        if instance.service.status == ServiceStatus.COMPLETED:
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

        # Cancel any pending stock requests for this item
        from inventory.models import StockRequest
        StockRequest.objects.filter(
            service_item=instance, status='pending'
        ).update(status='cancelled')

        service = instance.service

        result = super().destroy(request, *args, **kwargs)

        from services.business_logic import RevenueCalculator, ServicePaymentManager
        RevenueCalculator.calculate_service_revenue(service, save=True)
        ServicePaymentManager.sync_sales_items(service)
        self._reset_service_items_checked(service)

        return result

    def _reset_service_items_checked(self, service):
        """Reset service_items_checked if it was confirmed, and re-notify clerks."""
        if service.service_items_checked:
            service.service_items_checked = False
            service.service_items_checked_by = None
            service.service_items_checked_at = None
            service.save(
                update_fields=[
                    "service_items_checked",
                    "service_items_checked_by",
                    "service_items_checked_at",
                ],
                skip_validation=True,
            )
            if service.service_parts_needed_notes:
                try:
                    from accounts.models import CustomUser
                    from notifications.models import Notification, NotificationType

                    clerks = CustomUser.objects.filter(role="clerk", is_active=True)
                    Notification.objects.bulk_create([
                        Notification(
                            user=clerk,
                            type=NotificationType.ITEMS_PENDING_REVIEW,
                            title="Service items need re-review",
                            message=(
                                f"Service-level parts were changed on service #{service.id} "
                                f"({service.client}). Please re-confirm items."
                            ),
                            data={"service_id": service.id},
                        )
                        for clerk in clerks
                    ])
                except Exception:
                    pass


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


# --------------------------
# Service Receipt ViewSet
# --------------------------
class ServiceReceiptViewSet(viewsets.ModelViewSet):
    """
    CRUD for receipts associated with a service.
    A service may have multiple receipts (partial payments).
    """

    serializer_class = ServiceReceiptSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = ServiceReceipt.objects.select_related("service")
        service_id = self.request.query_params.get("service")
        if service_id:
            qs = qs.filter(service_id=service_id)
        return qs


class JobOrderTemplatePrintViewSet(viewsets.ModelViewSet):
    """Tracks printed job order template batches."""

    serializer_class = JobOrderTemplatePrintSerializer
    permission_classes = [IsAdminOrManager]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return JobOrderTemplatePrint.objects.select_related("printed_by")

    def perform_create(self, serializer):
        instance = serializer.save(printed_by=self.request.user)
        # Push WS event so other connected users see the update
        from analytics.ws_utils import push_dashboard_event

        push_dashboard_event(
            "jo_template_printed",
            {
                "start_number": instance.start_number,
                "end_number": instance.end_number,
                "printed_by": instance.printed_by.get_full_name(),
                "printed_at": instance.printed_at.isoformat(),
            },
        )

    @action(detail=False, methods=["get"])
    def next_number(self, request):
        """Returns the suggested next starting job order number."""
        latest = JobOrderTemplatePrint.objects.order_by("-end_number").first()
        next_num = (latest.end_number + 1) if latest else 1
        return Response({"next_number": next_num})


# --------------------------
# Company Asset ViewSet
# --------------------------
class CompanyAssetViewSet(viewsets.ModelViewSet):
    """
    CRUD + status management for company-owned (forfeited / acquired) appliances.

    Endpoints:
    - GET  /company-assets/              – list with optional ?service=, ?status=, ?acquisition_type=
    - POST /company-assets/              – create (used by convert_to_acquisition action internally)
    - GET  /company-assets/{id}/         – detail
    - PATCH /company-assets/{id}/        – update status / notes
    - POST /company-assets/{id}/dispose/ – mark as disposed/sold
    """

    serializer_class = CompanyAssetSerializer
    permission_classes = [IsAdminOrManager]
    filterset_fields = ["status", "acquisition_type", "service"]
    ordering_fields = ["acquired_at", "status", "id"]
    ordering = ["-acquired_at"]

    def get_queryset(self):
        qs = CompanyAsset.objects.select_related(
            "service__client", "service_appliance", "acquired_by"
        )
        return qs

    def perform_create(self, serializer):
        serializer.save(acquired_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="dispose")
    def dispose(self, request, pk=None):
        """Mark asset as sold, repurposed, or disposed."""
        asset = self.get_object()
        new_status = request.data.get("status")
        valid = [s[0] for s in CompanyAsset.AssetStatus.choices]
        if new_status not in valid:
            return Response(
                {"detail": f"status must be one of: {valid}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from django.utils import timezone as tz

        asset.status = new_status
        asset.disposal_notes = request.data.get("disposal_notes", "")
        if new_status in (CompanyAsset.AssetStatus.SOLD, CompanyAsset.AssetStatus.DISPOSED, CompanyAsset.AssetStatus.REPURPOSED):
            asset.disposed_at = tz.now()

        # Sale-specific fields
        if new_status == CompanyAsset.AssetStatus.SOLD:
            sale_price = request.data.get("sale_price")
            if sale_price is not None:
                asset.sale_price = sale_price

            sold_to_id = request.data.get("sold_to")
            if sold_to_id:
                from clients.models import Client
                try:
                    client = Client.objects.get(pk=sold_to_id)
                    asset.sold_to = client
                except Client.DoesNotExist:
                    return Response(
                        {"detail": "Client not found."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                asset.sold_to = None

            # Auto-create a SalesTransaction for revenue tracking
            if sale_price and sold_to_id:
                from decimal import Decimal
                from sales.models import (
                    SalesTransaction,
                    SalesItem,
                    SalesPayment,
                    TransactionType,
                    PaymentStatus,
                )

                stall = asset.service.stall
                tx = SalesTransaction.objects.create(
                    stall=stall,
                    client=asset.sold_to,
                    sales_clerk=request.user,
                    transaction_type=TransactionType.ASSET_SALE,
                    payment_status=PaymentStatus.UNPAID,
                    note=f"Asset sale: {asset.appliance_description}",
                    transaction_date=tz.now().date(),
                )
                SalesItem.objects.create(
                    transaction=tx,
                    description=asset.appliance_description,
                    quantity=1,
                    final_price_per_unit=Decimal(str(sale_price)),
                )
                # Create payment record (cash) so it's marked as paid
                payment_type = request.data.get("payment_type", "cash")
                SalesPayment.objects.create(
                    transaction=tx,
                    payment_type=payment_type,
                    amount=Decimal(str(sale_price)),
                )

        asset.save()
        return Response(CompanyAssetSerializer(asset).data)
