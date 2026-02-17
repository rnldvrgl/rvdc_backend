"""
Business logic for aircon unit sales and installation workflows.

This module handles:
- Aircon unit inventory management (Main stall)
- Aircon sales transactions
- Installation service integration
- Revenue attribution to Main stall
- Warranty tracking
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError


def get_main_stall():
    """Get the Main stall (services + aircon units)."""
    from inventory.models import Stall
    return Stall.objects.filter(stall_type='main', is_system=True).first()


def _create_schedule_for_service(service, scheduled_date=None, scheduled_time=None,
                                  schedule_type='home_service', user=None):
    """
    Auto-create a Schedule record for a service.

    Used by installation, warranty, and free-cleaning handlers so every
    home-service or pull-out service gets a schedule automatically.
    """
    from datetime import time as dt_time

    from schedules.models import Schedule

    if not scheduled_date:
        return None

    sch = Schedule.objects.create(
        client=service.client,
        service=service,
        schedule_type=schedule_type,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time or dt_time(9, 0),
        estimated_duration=60,
        status='pending',
        address=service.override_address or (service.client.address if service.client else ''),
        contact_person=service.override_contact_person or (service.client.full_name if service.client else ''),
        contact_number=service.override_contact_number or (service.client.contact_number if service.client else ''),
        notes=service.description,
        created_by=user,
    )
    return sch


class AirconInventoryManager:
    """Manages aircon unit inventory for Main stall."""

    @staticmethod
    def get_available_units(model=None, brand=None):
        """
        Get available aircon units for sale.

        Args:
            model: Optional AirconModel to filter by
            brand: Optional AirconBrand to filter by

        Returns:
            QuerySet of available units
        """
        from installations.models import AirconUnit

        queryset = AirconUnit.objects.filter(
            sale__isnull=True,
            is_sold=False,
            reserved_by__isnull=True
        ).select_related('model', 'model__brand', 'stall')

        if model:
            queryset = queryset.filter(model=model)

        if brand:
            queryset = queryset.filter(model__brand=brand)

        return queryset

    @staticmethod
    def reserve_unit(unit, client, user=None):
        """
        Reserve an aircon unit for a client.

        Args:
            unit: AirconUnit instance
            client: Client reserving the unit
            user: User making the reservation (optional)

        Returns:
            Updated AirconUnit instance

        Raises:
            ValidationError: If unit is not available
        """
        from django.utils import timezone

        with transaction.atomic():
            # Lock the unit
            from installations.models import AirconUnit
            unit = AirconUnit.objects.select_for_update().get(pk=unit.pk)

            # Check availability
            if not unit.is_available_for_sale:
                raise ValidationError(
                    f"Unit {unit.serial_number} is not available for reservation."
                )

            # Reserve unit
            unit.reserved_by = client
            unit.reserved_at = timezone.now()
            unit.save(update_fields=['reserved_by', 'reserved_at', 'updated_at'])

            return unit

    @staticmethod
    def release_reservation(unit):
        """
        Release a reservation on an aircon unit.

        Args:
            unit: AirconUnit instance

        Returns:
            Updated AirconUnit instance
        """
        with transaction.atomic():
            from installations.models import AirconUnit
            unit = AirconUnit.objects.select_for_update().get(pk=unit.pk)

            unit.reserved_by = None
            unit.reserved_at = None
            unit.save(update_fields=['reserved_by', 'reserved_at', 'updated_at'])

            return unit

    @staticmethod
    def check_stock_level(model=None):
        """
        Check stock levels for aircon units.

        Args:
            model: Optional AirconModel to check

        Returns:
            dict with stock information
        """
        from installations.models import AirconUnit

        queryset = AirconUnit.objects.all()
        if model:
            queryset = queryset.filter(model=model)

        total = queryset.count()
        available = queryset.filter(
            sale__isnull=True,
            is_sold=False,
            reserved_by__isnull=True
        ).count()
        reserved = queryset.filter(reserved_by__isnull=False).count()
        sold = queryset.filter(is_sold=True).count()

        return {
            'total': total,
            'available': available,
            'reserved': reserved,
            'sold': sold,
        }


class AirconSalesHandler:
    """Handles aircon unit sales transactions."""

    @staticmethod
    def sell_unit(unit, client, sales_clerk=None, payment_type='cash',
                  create_transaction=True):
        """
        Sell an aircon unit to a client.

        Args:
            unit: AirconUnit instance to sell
            client: Client purchasing the unit
            sales_clerk: User making the sale (optional)
            payment_type: Payment method
            create_transaction: If True, creates SalesTransaction

        Returns:
            dict with sale information

        Raises:
            ValidationError: If unit is not available for sale
        """
        with transaction.atomic():
            from sales.models import SalesItem, SalesPayment, SalesTransaction

            from installations.models import AirconUnit

            # Lock the unit
            unit = AirconUnit.objects.select_for_update().get(pk=unit.pk)

            # Validate availability
            if unit.is_sold or unit.sale:
                raise ValidationError(
                    f"Unit {unit.serial_number} has already been sold."
                )

            if not unit.model:
                raise ValidationError("Unit must have a model assigned.")

            # Get Main stall
            main_stall = get_main_stall()
            if not main_stall:
                raise ValidationError("Main stall not configured in system.")

            # Ensure unit belongs to Main stall
            if not unit.stall:
                unit.stall = main_stall
                unit.save(update_fields=['stall', 'updated_at'])

            # Get sale price
            sale_price = unit.sale_price

            # Create sales transaction if requested
            sales_transaction = None
            if create_transaction:
                sales_transaction = SalesTransaction.objects.create(
                    stall=main_stall,
                    client=client,
                    sales_clerk=sales_clerk,
                )

                # Add aircon unit as sales item
                SalesItem.objects.create(
                    transaction=sales_transaction,
                    item=None,  # Aircon is not inventory item
                    description=f"Aircon Unit: {unit.model} (SN: {unit.serial_number})",
                    quantity=1,
                    final_price_per_unit=sale_price,
                )

                # Create payment if cash
                if payment_type == 'cash':
                    SalesPayment.objects.create(
                        transaction=sales_transaction,
                        payment_type='cash',
                        amount=sale_price,
                    )

                # Link sale to unit
                unit.sale = sales_transaction

            # Mark unit as sold
            unit.is_sold = True
            unit.reserved_by = None
            unit.reserved_at = None
            unit.save(update_fields=[
                'sale', 'is_sold', 'reserved_by', 'reserved_at',
                'warranty_start_date', 'updated_at'
            ])

            return {
                'unit': unit,
                'sale_transaction': sales_transaction,
                'sale_price': sale_price,
                'client': client,
            }

    @staticmethod
    def sell_multiple_units(units, client, sales_clerk=None, payment_type='cash'):
        """
        Sell multiple aircon units in a single transaction.

        Args:
            units: List of AirconUnit instances
            client: Client purchasing the units
            sales_clerk: User making the sale
            payment_type: Payment method

        Returns:
            dict with sale information
        """
        from sales.models import SalesItem, SalesPayment, SalesTransaction

        main_stall = get_main_stall()
        if not main_stall:
            raise ValidationError("Main stall not configured in system.")

        with transaction.atomic():
            # Create single sales transaction
            sales_transaction = SalesTransaction.objects.create(
                stall=main_stall,
                client=client,
                sales_clerk=sales_clerk,
            )

            total_amount = Decimal('0.00')
            sold_units = []

            for unit in units:
                # Validate and sell each unit
                result = AirconSalesHandler.sell_unit(
                    unit=unit,
                    client=client,
                    sales_clerk=sales_clerk,
                    payment_type=payment_type,
                    create_transaction=False,  # We're creating one transaction
                )

                # Add to existing transaction
                SalesItem.objects.create(
                    transaction=sales_transaction,
                    item=None,
                    description=f"Aircon Unit: {unit.model} (SN: {unit.serial_number})",
                    quantity=1,
                    final_price_per_unit=result['sale_price'],
                )

                # Link sale to unit
                unit.sale = sales_transaction
                unit.save(update_fields=['sale', 'updated_at'])

                total_amount += result['sale_price']
                sold_units.append(unit)

            # Create payment if cash
            if payment_type == 'cash':
                SalesPayment.objects.create(
                    transaction=sales_transaction,
                    payment_type=payment_type,
                    amount=total_amount,
                )

            return {
                'units': sold_units,
                'sale_transaction': sales_transaction,
                'total_amount': total_amount,
                'client': client,
            }


class AirconInstallationHandler:
    """Handles aircon installation workflows."""

    @staticmethod
    def create_installation_service(unit, client, scheduled_date=None,
                                   scheduled_time=None, labor_fee=None,
                                   labor_is_free=False,
                                   user=None,
                                   sell_unit_now=False,
                                   payment_type='cash'):
        """
        Create installation service for an aircon unit.

        Args:
            unit: AirconUnit instance
            client: Client for the installation
            scheduled_date: Date of installation
            scheduled_time: Time of installation
            labor_fee: Labor fee for installation
            labor_is_free: Mark labor as free (promotional)
            user: User creating the service
            sell_unit_now: If True, sell the unit now (if not already sold)
            payment_type: Payment method if selling unit now

        Returns:
            dict with service and installation details
        """
        from services.business_logic import (
            RevenueCalculator,
        )
        from services.models import Service, ServiceAppliance
        from utils.enums import ServiceMode, ServiceStatus, ServiceType

        main_stall = get_main_stall()
        if not main_stall:
            raise ValidationError("Main stall not configured in system.")

        # Check if unit needs to be sold first (optional)
        sale_transaction = None
        if sell_unit_now and not unit.is_sold:
            # Sell the unit now
            sale_result = AirconSalesHandler.sell_unit(
                unit=unit,
                client=client,
                sales_clerk=user,
                payment_type=payment_type,
                create_transaction=True
            )
            unit = sale_result['unit']  # Get updated unit
            sale_transaction = sale_result.get('sale_transaction')
        elif not unit.is_sold:
            # Reserve the unit for this client
            unit.reserved_by = client
            unit.reserved_at = timezone.now()
            unit.save(update_fields=['reserved_by', 'reserved_at', 'updated_at'])

        with transaction.atomic():
            # Create installation service
            service = Service.objects.create(
                client=client,
                stall=main_stall,
                service_type=ServiceType.INSTALLATION,
                service_mode=ServiceMode.HOME_SERVICE,
                scheduled_date=scheduled_date,
                scheduled_time=scheduled_time,
                status=ServiceStatus.PENDING,
                description=f"Installation for Aircon Unit: {unit.model} (SN: {unit.serial_number})",
                notes=f"Unit: {unit.serial_number}, Model: {unit.model}",
            )

            # Link unit to installation service
            unit.installation_service = service
            unit.save(update_fields=['installation_service', 'updated_at'])

            # Create service appliance for the aircon
            appliance = ServiceAppliance.objects.create(
                service=service,
                appliance_type=None,  # This is an aircon installation
                brand=unit.model.brand.name if unit.model else None,
                model=unit.model.name if unit.model else None,
                serial_number=unit.serial_number,  # Add serial number
                labor_fee=labor_fee or Decimal('0.00'),
                labor_is_free=labor_is_free,
                labor_original_amount=labor_fee if labor_is_free and labor_fee > 0 else None,
            )

            # Calculate initial revenue
            RevenueCalculator.calculate_service_revenue(service, save=True)

            # Auto-create schedule for home service installation
            schedule = _create_schedule_for_service(
                service,
                scheduled_date=scheduled_date,
                scheduled_time=scheduled_time,
                schedule_type='home_service',
                user=user,
            )

            return {
                'service': service,
                'sale_transaction': sale_transaction,  # Include sale transaction if created
                'unit_price': unit.sale_price,  # Include unit price for reference
                'unit': unit,
                'appliance': appliance,
                'schedule': schedule,
            }

    @staticmethod
    def complete_installation(service, completion_date=None, user=None):
        """
        Complete an aircon installation service.

        Args:
            service: Service instance (must be INSTALLATION type)
            completion_date: Date of completion
            user: User completing the installation

        Returns:
            dict with completion details
        """
        from services.business_logic import ServiceCompletionHandler
        from utils.enums import ServiceStatus, ServiceType

        if service.service_type != ServiceType.INSTALLATION:
            raise ValidationError("Service must be an INSTALLATION service.")

        if service.status == ServiceStatus.COMPLETED:
            raise ValidationError("Installation is already completed.")

        with transaction.atomic():
            # Complete the service (consumes stock, creates transactions)
            result = ServiceCompletionHandler.complete_service(
                service=service,
                user=user,
                create_receipt=True
            )

            # Warranty starts on installation completion date
            warranty_date = completion_date if completion_date else timezone.now().date()
            
            # Activate warranties for aircon units
            units = service.installation_units.all()
            for unit in units:
                unit.warranty_start_date = warranty_date
                unit.save(update_fields=['warranty_start_date', 'updated_at'])
            
            # Activate warranties for service appliances (labor and unit warranties)
            appliances = service.appliances.all()
            for appliance in appliances:
                appliance.activate_warranties(start_date=warranty_date)

            return {
                'service': service,
                'completion_result': result,
                'units': list(units),
            }


class AirconRevenueTracker:
    """Tracks aircon unit sales revenue for Main stall."""

    @staticmethod
    def calculate_aircon_revenue(service=None, start_date=None, end_date=None):
        """
        Calculate aircon revenue for Main stall.

        Args:
            service: Optional specific service
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            dict with revenue breakdown
        """

        from installations.models import AirconUnit

        main_stall = get_main_stall()
        if not main_stall:
            return {
                'total_units_sold': 0,
                'total_revenue': Decimal('0.00'),
            }

        # Get sold units
        units = AirconUnit.objects.filter(
            stall=main_stall,
            is_sold=True,
            sale__isnull=False
        )

        if start_date:
            units = units.filter(sale__created_at__gte=start_date)
        if end_date:
            units = units.filter(sale__created_at__lte=end_date)

        # Calculate revenue
        total_revenue = Decimal('0.00')
        for unit in units:
            total_revenue += unit.sale_price

        return {
            'total_units_sold': units.count(),
            'total_revenue': total_revenue,
            'units': units,
        }

    @staticmethod
    def get_installation_revenue(start_date=None, end_date=None):
        """
        Get installation service revenue (labor fees).

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            dict with installation revenue
        """
        from django.db.models import Sum
        from services.models import Service
        from utils.enums import ServiceStatus, ServiceType

        queryset = Service.objects.filter(
            service_type=ServiceType.INSTALLATION,
            status=ServiceStatus.COMPLETED
        )

        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        # Sum main stall revenue (labor fees)
        total_labor_revenue = queryset.aggregate(
            total=Sum('main_stall_revenue')
        )['total'] or Decimal('0.00')

        return {
            'total_installations': queryset.count(),
            'labor_revenue': total_labor_revenue,
            'services': queryset,
        }


# Convenience functions

def reserve_aircon_unit(unit, client, user=None):
    """Reserve an aircon unit for a client."""
    return AirconInventoryManager.reserve_unit(unit, client, user)


def sell_aircon_unit(unit, client, sales_clerk=None, payment_type='cash'):
    """Sell an aircon unit to a client."""
    return AirconSalesHandler.sell_unit(unit, client, sales_clerk, payment_type)


def create_aircon_installation(unit, client, **kwargs):
    """Create installation service for a sold aircon unit."""
    return AirconInstallationHandler.create_installation_service(unit, client, **kwargs)


def get_available_aircons(model=None, brand=None):
    """Get available aircon units for sale."""
    return AirconInventoryManager.get_available_units(model, brand)


# ============================================================================
# Warranty Management
# ============================================================================


class WarrantyEligibilityChecker:
    """Check warranty eligibility for aircon units."""

    @staticmethod
    def check_eligibility(unit):
        """
        Check if a unit is eligible for warranty service.

        Args:
            unit: AirconUnit instance

        Returns:
            dict with 'eligible' (bool) and 'reason' (str) keys

        Raises:
            ValidationError if unit is invalid
        """
        if not unit:
            raise ValidationError("Unit is required")

        # Unit must have been installed (no need to be sold - payment can be pending)
        if unit.unit_status != "Installed":
            return {
                'eligible': False,
                'reason': 'Unit has not been installed yet',
            }

        # Unit must have warranty
        if unit.warranty_period_months == 0:
            return {
                'eligible': False,
                'reason': 'Unit has no warranty coverage',
            }

        # Warranty must have started
        if not unit.warranty_start_date:
            return {
                'eligible': False,
                'reason': 'Warranty has not started yet',
            }

        # Check if under warranty
        if not unit.is_under_warranty:
            return {
                'eligible': False,
                'reason': f'Warranty has expired. Warranty ended on {unit.warranty_end_date}',
                'warranty_end_date': unit.warranty_end_date,
            }

        # All checks passed
        return {
            'eligible': True,
            'reason': 'Unit is under warranty',
            'warranty_days_left': unit.warranty_days_left,
            'warranty_end_date': unit.warranty_end_date,
        }


class WarrantyClaimManager:
    """Manages warranty claim lifecycle."""

    @staticmethod
    @transaction.atomic
    def create_claim(unit, issue_description, claim_type='repair', customer_notes='', **kwargs):
        """
        Create a warranty claim for an aircon unit.

        Args:
            unit: AirconUnit instance
            issue_description: Description of the issue
            claim_type: Type of claim (repair, replacement, parts, inspection)
            customer_notes: Additional notes from customer
            **kwargs: Additional fields for WarrantyClaim

        Returns:
            WarrantyClaim instance

        Raises:
            ValidationError if unit is not eligible for warranty
        """
        from installations.models import WarrantyClaim

        # Check eligibility
        eligibility = WarrantyEligibilityChecker.check_eligibility(unit)
        if not eligibility['eligible']:
            raise ValidationError({
                'unit': f"Unit is not eligible for warranty claim: {eligibility['reason']}"
            })

        # Create claim
        claim = WarrantyClaim.objects.create(
            unit=unit,
            claim_type=claim_type,
            issue_description=issue_description,
            customer_notes=customer_notes,
            **kwargs
        )

        return claim

    @staticmethod
    @transaction.atomic
    def approve_claim(claim, reviewed_by, technician_assessment='', create_service=True):
        """
        Approve a warranty claim and optionally create a service.

        Args:
            claim: WarrantyClaim instance
            reviewed_by: CustomUser who is approving
            technician_assessment: Assessment notes
            create_service: Whether to auto-create service

        Returns:
            dict with 'claim' and optional 'service' keys

        Raises:
            ValidationError if claim cannot be approved
        """
        from django.utils import timezone

        from installations.models import WarrantyClaim

        if claim.status != WarrantyClaim.ClaimStatus.PENDING:
            raise ValidationError(f"Cannot approve claim with status '{claim.get_status_display()}'")

        # Update claim
        claim.status = WarrantyClaim.ClaimStatus.APPROVED
        claim.reviewed_by = reviewed_by
        claim.reviewed_at = timezone.now()
        claim.is_valid_claim = True
        if technician_assessment:
            claim.technician_assessment = technician_assessment
        claim.save()

        result = {'claim': claim}

        # Create service if requested
        if create_service:
            service = WarrantyServiceHandler.create_warranty_service(claim)
            result['service'] = service

        return result

    @staticmethod
    @transaction.atomic
    def reject_claim(claim, reviewed_by, rejection_reason, is_valid_claim=False):
        """
        Reject a warranty claim.

        Args:
            claim: WarrantyClaim instance
            reviewed_by: CustomUser who is rejecting
            rejection_reason: Reason for rejection
            is_valid_claim: Whether claim was valid (affects warranty status)

        Returns:
            WarrantyClaim instance

        Raises:
            ValidationError if claim cannot be rejected
        """
        from django.utils import timezone

        from installations.models import WarrantyClaim

        if claim.status != WarrantyClaim.ClaimStatus.PENDING:
            raise ValidationError(f"Cannot reject claim with status '{claim.get_status_display()}'")

        if not rejection_reason:
            raise ValidationError("Rejection reason is required")

        # Update claim
        claim.status = WarrantyClaim.ClaimStatus.REJECTED
        claim.reviewed_by = reviewed_by
        claim.reviewed_at = timezone.now()
        claim.rejection_reason = rejection_reason
        claim.is_valid_claim = is_valid_claim
        claim.save()

        return claim

    @staticmethod
    @transaction.atomic
    def cancel_claim(claim, cancellation_reason=''):
        """
        Cancel a warranty claim.

        Args:
            claim: WarrantyClaim instance
            cancellation_reason: Reason for cancellation

        Returns:
            WarrantyClaim instance
        """
        from installations.models import WarrantyClaim

        if claim.status == WarrantyClaim.ClaimStatus.COMPLETED:
            raise ValidationError("Cannot cancel a completed claim")

        if claim.status == WarrantyClaim.ClaimStatus.CANCELLED:
            raise ValidationError("Claim is already cancelled")

        # Cancel linked service if exists
        if claim.service and claim.service.status != 'completed':
            from services.business_logic import ServiceCancellationHandler
            ServiceCancellationHandler.cancel_service(claim.service)

        # Update claim
        claim.status = WarrantyClaim.ClaimStatus.CANCELLED
        if cancellation_reason:
            claim.customer_notes += f"\n\nCancellation reason: {cancellation_reason}"
        claim.save()

        return claim

    @staticmethod
    @transaction.atomic
    def complete_claim(claim):
        """
        Mark a warranty claim as completed.

        Args:
            claim: WarrantyClaim instance

        Returns:
            WarrantyClaim instance

        Raises:
            ValidationError if claim cannot be completed
        """
        from django.utils import timezone

        from installations.models import WarrantyClaim

        if claim.status == WarrantyClaim.ClaimStatus.COMPLETED:
            raise ValidationError("Claim is already completed")

        if claim.status not in [
            WarrantyClaim.ClaimStatus.APPROVED,
            WarrantyClaim.ClaimStatus.IN_PROGRESS,
        ]:
            raise ValidationError(
                f"Cannot complete claim with status '{claim.get_status_display()}'"
            )

        # Check if service is completed
        if claim.service and claim.service.status != 'completed':
            raise ValidationError(
                "Cannot complete claim - linked service is not completed yet"
            )

        # Update claim
        claim.status = WarrantyClaim.ClaimStatus.COMPLETED
        claim.completed_at = timezone.now()
        claim.save()

        return claim


class WarrantyServiceHandler:
    """Handles creation and management of warranty services."""

    @staticmethod
    @transaction.atomic
    def create_warranty_service(claim, scheduled_date=None, scheduled_time=None, **service_kwargs):
        """
        Create a service for a warranty claim.

        Args:
            claim: WarrantyClaim instance
            scheduled_date: Optional scheduled date
            scheduled_time: Optional scheduled time
            **service_kwargs: Additional Service fields

        Returns:
            Service instance

        Raises:
            ValidationError if service cannot be created
        """
        from services.models import Service
        from utils.enums import ServiceMode, ServiceStatus, ServiceType

        from installations.models import WarrantyClaim

        if claim.service:
            raise ValidationError("Warranty claim already has a service linked")

        if claim.status not in [
            WarrantyClaim.ClaimStatus.APPROVED,
            WarrantyClaim.ClaimStatus.IN_PROGRESS,
        ]:
            raise ValidationError(
                f"Cannot create service for claim with status '{claim.get_status_display()}'"
            )

        # Get client from unit sale
        if not claim.unit.sale:
            raise ValidationError("Cannot create service - unit has no sale record")

        client = claim.unit.sale.client

        # Determine service type from claim type
        service_type_map = {
            'repair': ServiceType.REPAIR,
            'replacement': ServiceType.REPAIR,
            'parts': ServiceType.REPAIR,
            'inspection': ServiceType.INSPECTION,
        }
        service_type = service_type_map.get(claim.claim_type, ServiceType.REPAIR)

        # Get main stall
        main_stall = get_main_stall()
        if not main_stall:
            raise ValidationError("Main stall not configured")

        # Create service
        service_data = {
            'client': client,
            'stall': main_stall,
            'service_type': service_type,
            'service_mode': service_kwargs.pop('service_mode', ServiceMode.HOME_SERVICE),
            'status': ServiceStatus.PENDING,
            'description': f"WARRANTY CLAIM #{claim.id}: {claim.issue_description}",
            'notes': f"Warranty claim for unit {claim.unit.serial_number}\n{claim.customer_notes}",
        }

        if scheduled_date:
            service_data['scheduled_date'] = scheduled_date
        if scheduled_time:
            service_data['scheduled_time'] = scheduled_time

        # Override with any additional kwargs
        service_data.update(service_kwargs)

        service = Service.objects.create(**service_data)

        # Link service to claim
        claim.service = service
        claim.status = WarrantyClaim.ClaimStatus.IN_PROGRESS
        claim.save()

        # Auto-create schedule for warranty service
        _create_schedule_for_service(
            service,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            schedule_type='home_service',
        )

        return service


class FreeCleaningManager:
    """Manages free cleaning redemption for aircon units."""

    @staticmethod
    @transaction.atomic
    def check_eligibility(unit):
        """
        Check if a unit is eligible for free cleaning redemption.

        Args:
            unit: AirconUnit instance

        Returns:
            dict with 'eligible' (bool) and 'reason' (str) keys
        """
        if not unit:
            raise ValidationError("Unit is required")

        # Unit must have been installed (no need to be sold - payment can be pending)
        if unit.unit_status != "Installed":
            return {
                'eligible': False,
                'reason': 'Unit has not been installed yet',
            }

        # Check if already redeemed
        if unit.free_cleaning_redeemed:
            return {
                'eligible': False,
                'reason': 'Free cleaning has already been redeemed',
            }

        # Check if within 1 year of installation (free cleaning validity period)
        if not unit.warranty_start_date:
            return {
                'eligible': False,
                'reason': 'Unit warranty has not started yet (not installed)',
            }
        
        from dateutil.relativedelta import relativedelta
        free_cleaning_deadline = unit.warranty_start_date + relativedelta(years=1)
        if timezone.now().date() > free_cleaning_deadline:
            return {
                'eligible': False,
                'reason': 'Free cleaning is only valid within 1 year of installation',
                'free_cleaning_deadline': free_cleaning_deadline,
            }

        # All checks passed
        return {
            'eligible': True,
            'reason': 'Unit is eligible for free cleaning',
            'warranty_days_left': unit.warranty_days_left,
        }

    @staticmethod
    @transaction.atomic
    def redeem_free_cleaning(unit, scheduled_date=None, scheduled_time=None, **service_kwargs):
        """
        Redeem free cleaning for an aircon unit and create cleaning service.

        Args:
            unit: AirconUnit instance
            scheduled_date: Required scheduled date for cleaning
            scheduled_time: Optional scheduled time for cleaning
            **service_kwargs: Additional Service fields

        Returns:
            dict with 'service' and 'unit' keys

        Raises:
            ValidationError if unit is not eligible or scheduled_date is missing
        """
        from services.models import Service
        from utils.enums import ServiceMode, ServiceStatus, ServiceType

        # Require scheduled date
        if not scheduled_date:
            raise ValidationError({
                'scheduled_date': 'A scheduled date is required for free cleaning redemption.'
            })

        # Check eligibility
        eligibility = FreeCleaningManager.check_eligibility(unit)
        if not eligibility['eligible']:
            raise ValidationError({
                'unit': f"Unit is not eligible for free cleaning: {eligibility['reason']}"
            })

        # Get client from unit sale or reservation
        client = None
        if unit.sale:
            client = unit.sale.client
        elif unit.reserved_by:
            client = unit.reserved_by

        if not client:
            raise ValidationError("Cannot create service - unit has no sale or reservation record")

        # Get main stall
        main_stall = get_main_stall()
        if not main_stall:
            raise ValidationError("Main stall not configured")

        # Create cleaning service
        service_data = {
            'client': client,
            'stall': main_stall,
            'service_type': ServiceType.CLEANING,
            'service_mode': service_kwargs.pop('service_mode', ServiceMode.HOME_SERVICE),
            'status': ServiceStatus.PENDING,
            'description': f"FREE CLEANING for {unit.model} (SN: {unit.serial_number})",
            'notes': f"Free cleaning redemption for warranty unit\nSerial Number: {unit.serial_number}",
        }

        if scheduled_date:
            service_data['scheduled_date'] = scheduled_date
        if scheduled_time:
            service_data['scheduled_time'] = scheduled_time

        # Override with any additional kwargs
        service_data.update(service_kwargs)

        service = Service.objects.create(**service_data)

        # Mark as redeemed and link service
        unit.free_cleaning_redeemed = True
        unit.free_cleaning_service = service
        unit.save()

        # Auto-create schedule for free cleaning service
        _create_schedule_for_service(
            service,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            schedule_type='home_service',
        )

        return {
            'service': service,
            'unit': unit,
        }

    @staticmethod
    def unredeemed_units(client=None):
        """
        Get units that haven't redeemed free cleaning yet.

        Args:
            client: Optional client to filter by

        Returns:
            QuerySet of AirconUnit instances
        """
        from installations.models import AirconUnit
        from utils.enums import ServiceStatus

        queryset = AirconUnit.objects.filter(
            free_cleaning_redeemed=False,
        ).filter(
            Q(is_sold=True) | Q(
                installation_service__isnull=False,
                installation_service__status=ServiceStatus.COMPLETED,
            )
        ).select_related('model', 'model__brand', 'sale', 'sale__client', 'reserved_by')

        if client:
            queryset = queryset.filter(
                Q(sale__client=client) | Q(reserved_by=client)
            )

        return queryset

    @staticmethod
    @transaction.atomic
    def redeem_free_cleaning_batch(units, client, scheduled_date=None, scheduled_time=None):
        """
        Redeem free cleaning for multiple aircon units under a single client.
        Creates a single cleaning service with each unit as an appliance.

        Args:
            units: list of AirconUnit instances
            client: Client instance
            scheduled_date: Required scheduled date for cleaning
            scheduled_time: Optional scheduled time for cleaning

        Returns:
            dict with 'service' and 'units' keys

        Raises:
            ValidationError if any unit is not eligible or scheduled_date is missing
        """
        from services.models import Service, ServiceAppliance
        from utils.enums import ServiceMode, ServiceStatus, ServiceType

        if not units:
            raise ValidationError("At least one unit is required")

        # Require scheduled date
        if not scheduled_date:
            raise ValidationError({
                'scheduled_date': 'A scheduled date is required for free cleaning redemption.'
            })

        # Validate all units
        ineligible = []
        for unit in units:
            eligibility = FreeCleaningManager.check_eligibility(unit)
            if not eligibility['eligible']:
                ineligible.append(f"{unit.serial_number}: {eligibility['reason']}")

        if ineligible:
            raise ValidationError({
                'unit_ids': f"Some units are not eligible: {'; '.join(ineligible)}"
            })

        # Get main stall
        main_stall = get_main_stall()
        if not main_stall:
            raise ValidationError("Main stall not configured")

        # Build description and notes
        serial_numbers = [u.serial_number for u in units]
        unit_details = [f"{u.model} (SN: {u.serial_number})" for u in units]

        service_data = {
            'client': client,
            'stall': main_stall,
            'service_type': ServiceType.CLEANING,
            'service_mode': ServiceMode.HOME_SERVICE,
            'status': ServiceStatus.PENDING,
            'description': f"FREE CLEANING - {len(units)} unit(s)",
            'notes': "Free cleaning redemption\n" + "\n".join(
                f"- {detail}" for detail in unit_details
            ),
        }

        service = Service.objects.create(**service_data)

        # Get or create cleaning appliance type
        from services.models import ApplianceType
        cleaning_type, _ = ApplianceType.objects.get_or_create(
            name__iexact="Aircon",
            defaults={"name": "Aircon"},
        )

        # Create appliances for each unit
        for unit in units:
            ServiceAppliance.objects.create(
                service=service,
                appliance_type=cleaning_type,
                brand=unit.model.brand.name if unit.model and unit.model.brand else "",
                model=unit.model.name if unit.model else "",
                serial_number=unit.serial_number,
                issue_reported="Free cleaning redemption",
                labor_fee=0,
                labor_is_free=True,
            )

            # Mark as redeemed and link service
            unit.free_cleaning_redeemed = True
            unit.free_cleaning_service = service
            unit.save(clean=False)

        # Auto-create schedule
        _create_schedule_for_service(
            service,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            schedule_type='home_service',
        )

        return {
            'service': service,
            'units': units,
        }


# ============================================================================
# Convenience Functions
# ============================================================================


def create_warranty_claim(unit, issue_description, **kwargs):
    """Create a warranty claim for an aircon unit."""
    return WarrantyClaimManager.create_claim(unit, issue_description, **kwargs)


def check_warranty_eligibility(unit):
    """Check if a unit is eligible for warranty service."""
    return WarrantyEligibilityChecker.check_eligibility(unit)


def redeem_free_cleaning(unit, **kwargs):
    """Redeem free cleaning for an aircon unit."""
    return FreeCleaningManager.redeem_free_cleaning(unit, **kwargs)


def check_free_cleaning_eligibility(unit):
    """Check if a unit is eligible for free cleaning redemption."""
    return FreeCleaningManager.check_eligibility(unit)
