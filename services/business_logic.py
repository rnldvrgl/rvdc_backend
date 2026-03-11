"""
Business logic for service operations in the two-stall architecture.

This module handles:
- Stock reservation when services are scheduled
- Stock consumption when services are completed
- Revenue attribution (Main vs Sub stall)
- Promo application (free installation, copper tube promos)
- Service cancellation and stock release
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone
from expenses.models import Expense, ExpenseItem
from inventory.models import Stall, Stock
from rest_framework.exceptions import ValidationError
from sales.models import SalesItem, SalesTransaction


def get_main_stall():
    """Get the Main stall (services + aircon units)."""
    return Stall.objects.filter(stall_type='main', is_system=True).first()


def get_sub_stall():
    """Get the Sub stall (parts inventory)."""
    return Stall.objects.filter(stall_type='sub', is_system=True).first()


class StockReservationManager:
    """Manages stock reservations for service parts."""

    @staticmethod
    def _get_tolerance_buffer(item, quantity):
        """
        Calculate the tolerance buffer for an item.

        Items like freon (kg) or copper tubes (ft) have a waste_tolerance_percentage
        that accounts for measurement imprecision when dispensing.

        Returns:
            Decimal: The tolerance buffer amount
            (e.g., 5% tolerance on 10kg = 0.5kg buffer)
        """
        tolerance_pct = getattr(item, 'waste_tolerance_percentage', None) or Decimal('0')
        if tolerance_pct > 0:
            return (Decimal(str(quantity)) * tolerance_pct / Decimal('100')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        return Decimal('0')

    @staticmethod
    def reserve_stock(item, quantity, stall_stock=None):
        """
        Reserve stock for a service part.

        If the item has a waste_tolerance_percentage, the availability check
        allows reservation when stock is within the tolerance range.
        For example: need 10kg freon, 5% tolerance → allow if available >= 9.50kg.

        Args:
            item: The Item to reserve
            quantity: Quantity to reserve
            stall_stock: Optional Stock instance; if None, auto-resolves Sub stall stock

        Returns:
            Stock instance with reservation applied

        Raises:
            ValidationError: If insufficient stock available (beyond tolerance)
        """
        with transaction.atomic():
            if stall_stock is None:
                # Auto-resolve to Sub stall stock
                sub_stall = get_sub_stall()
                if not sub_stall:
                    raise ValidationError("Sub stall not configured in system.")

                stall_stock = Stock.objects.select_for_update().filter(
                    item=item,
                    stall=sub_stall,
                    is_deleted=False
                ).first()

                if not stall_stock:
                    raise ValidationError(f"No stock found for {item.name} in Sub stall.")
            else:
                # Lock the provided stock row
                stall_stock = Stock.objects.select_for_update().get(pk=stall_stock.pk)

            # Check available quantity (total - reserved)
            available = stall_stock.quantity - stall_stock.reserved_quantity
            quantity_dec = Decimal(str(quantity))

            # Apply waste tolerance: allow reservation if stock is within tolerance
            tolerance_buffer = StockReservationManager._get_tolerance_buffer(item, quantity_dec)
            minimum_required = max(quantity_dec - tolerance_buffer, Decimal('0'))

            if available < minimum_required:
                tolerance_note = ""
                if tolerance_buffer > 0:
                    tolerance_note = f" (with {item.waste_tolerance_percentage}% waste tolerance)"
                raise ValidationError(
                    f"Insufficient stock for {item.name}{tolerance_note}. "
                    f"Available: {available}, Requested: {quantity}"
                )

            # Reserve the requested amount (not the tolerance-adjusted minimum)
            # If available < quantity but >= minimum_required, reserve what's available
            actual_reserve = min(quantity_dec, available)
            stall_stock.reserved_quantity += actual_reserve
            stall_stock.save(update_fields=['reserved_quantity', 'updated_at'])

            return stall_stock

    @staticmethod
    def release_reservation(item, quantity, stall_stock):
        """
        Release a stock reservation (e.g., when service is cancelled).

        Args:
            item: The Item to release
            quantity: Quantity to release
            stall_stock: Stock instance to release from
        """
        with transaction.atomic():
            stock = Stock.objects.select_for_update().get(pk=stall_stock.pk)
            quantity_dec = Decimal(str(quantity))

            if stock.reserved_quantity < quantity_dec:
                # Defensive: don't allow negative reservations
                quantity_dec = stock.reserved_quantity

            stock.reserved_quantity -= quantity_dec
            stock.save(update_fields=['reserved_quantity', 'updated_at'])

    @staticmethod
    def consume_reservation(item, quantity, stall_stock):
        """
        Convert reservation to actual consumption (deduct from quantity and reserved_quantity).

        Tolerance-aware: If the item has waste_tolerance_percentage, the actual
        consumption may differ slightly from the reserved amount. The method
        handles the case where actual usage exceeds reservation within tolerance
        by adjusting the reserved_quantity accordingly.

        Args:
            item: The Item to consume
            quantity: Actual quantity consumed (may differ from reserved)
            stall_stock: Stock instance to consume from

        Raises:
            ValidationError: If insufficient reserved or total stock
        """
        with transaction.atomic():
            stock = Stock.objects.select_for_update().get(pk=stall_stock.pk)
            quantity_dec = Decimal(str(quantity))

            # For items with waste tolerance, actual consumption may slightly
            # exceed the reserved amount. Allow this within the tolerance range.
            if quantity_dec > stock.reserved_quantity:
                tolerance_buffer = StockReservationManager._get_tolerance_buffer(
                    item, quantity_dec
                )
                over_reserved = quantity_dec - stock.reserved_quantity
                if over_reserved > tolerance_buffer:
                    raise ValidationError(
                        f"Cannot consume {quantity} of {item.name}: only "
                        f"{stock.reserved_quantity} reserved "
                        f"(tolerance allows +{tolerance_buffer})."
                    )
                # Within tolerance: adjust reserved to match actual
                # (so the deduction below zeroes it cleanly)
                stock.reserved_quantity = quantity_dec

            if quantity_dec > stock.quantity:
                raise ValidationError(
                    f"Cannot consume {quantity} of {item.name}: only {stock.quantity} in stock."
                )

            # Deduct from both reserved and actual quantity
            stock.reserved_quantity -= quantity_dec
            stock.quantity -= quantity_dec
            stock.save(update_fields=['reserved_quantity', 'quantity', 'updated_at'])


class PromoManager:
    """Manages promotional pricing for services."""

    PROMO_FREE_INSTALLATION = "Free Installation Promo"
    PROMO_COPPER_TUBE_10FT = "Free 10ft Copper Tube Promo"

    @staticmethod
    def apply_free_installation(service_appliance):
        """
        Apply free installation promo to a service appliance.
        Sets labor_fee to 0 and stores original amount.

        Args:
            service_appliance: ServiceAppliance instance
        """
        if service_appliance.labor_fee > 0 and not service_appliance.labor_is_free:
            service_appliance.labor_original_amount = service_appliance.labor_fee
            service_appliance.labor_fee = Decimal('0.00')
            service_appliance.labor_is_free = True

    @staticmethod
    def apply_copper_tube_free_10ft(appliance_item_used, copper_tube_item_sku='CPR'):
        """
        Apply free first 10ft copper tube promo.

        Args:
            appliance_item_used: ApplianceItemUsed instance
            copper_tube_item_sku: SKU prefix for copper tube items

        Returns:
            tuple: (free_qty, charged_qty, promo_applied)
        """
        item = appliance_item_used.item
        quantity = appliance_item_used.quantity

        # Check if this is a copper tube item (by SKU or unit of measure)
        is_copper_tube = (
            item.sku.startswith(copper_tube_item_sku) or
            item.unit_of_measure == 'ft' and 'copper' in item.name.lower()
        )

        if not is_copper_tube:
            return 0, quantity, False

        # First 10ft free, rest charged
        free_qty = min(quantity, 10)
        charged_qty = max(quantity - 10, 0)

        appliance_item_used.free_quantity = free_qty
        appliance_item_used.promo_name = PromoManager.PROMO_COPPER_TUBE_10FT

        return free_qty, charged_qty, True


class RevenueCalculator:
    """Calculates revenue attribution for two-stall architecture."""

    @staticmethod
    def calculate_service_revenue(service, save=True):
        """
        Calculate and update revenue attribution for a service.

        Main stall revenue: Labor fees + aircon units sold
        Sub stall revenue: Parts (charged quantities only, excluding free items)

        Args:
            service: Service instance
            save: If True, save the service with updated revenue fields

        Returns:
            dict with keys: main_revenue, sub_revenue, total_revenue
        """
        main_revenue = Decimal('0.00')
        sub_revenue = Decimal('0.00')

        # Pre-build set of installation unit serial numbers
        # so we don't double-count brand_new unit prices
        installation_unit_serials = set()
        if service.service_type == 'installation':
            installation_unit_serials = set(
                service.installation_units.values_list('serial_number', flat=True)
            )

        # Calculate labor fees (Main stall revenue) with discounts
        for appliance in service.appliances.all():
            # Use discounted_labor_fee which accounts for labor discounts
            main_revenue += appliance.discounted_labor_fee or Decimal('0.00')
            # Add unit_price only for second-hand / non-installation appliances.
            # Brand-new installation units are handled in the installation_units loop below.
            if appliance.unit_price and appliance.serial_number not in installation_unit_serials:
                main_revenue += appliance.unit_price

        # Add aircon unit prices for installation services (Main stall revenue)
        if service.service_type == 'installation':
            for unit in service.installation_units.all():
                if unit.model:
                    # Check if there's an appliance with a custom unit_price override
                    matching_appliance = service.appliances.filter(
                        serial_number=unit.serial_number
                    ).first()
                    if matching_appliance and matching_appliance.unit_price:
                        main_revenue += matching_appliance.unit_price
                    else:
                        # Use selling_price which is promo_price if set, else retail
                        main_revenue += unit.model.selling_price

        # Calculate parts revenue (Sub stall revenue) with discounts
        for appliance in service.appliances.all():
            for item_used in appliance.items_used.all():
                # Use line_total which already accounts for discounts and free quantities
                sub_revenue += item_used.line_total

        total_revenue = main_revenue + sub_revenue

        # Apply service-level discount (percentage or fixed amount) to main stall only
        # Service-level discounts reduce labor/service fees, not parts
        service_discount = Decimal('0.00')
        if service.service_discount_percentage and service.service_discount_percentage > 0:
            service_discount = (total_revenue * service.service_discount_percentage / Decimal('100')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        elif service.service_discount_amount and service.service_discount_amount > 0:
            service_discount = service.service_discount_amount

        main_revenue = max(main_revenue - service_discount, Decimal('0.00'))
        total_revenue = main_revenue + sub_revenue
        
        # Round all revenue values to 2 decimal places to prevent validation errors
        main_revenue = main_revenue.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        sub_revenue = sub_revenue.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_revenue = total_revenue.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if save:
            service.main_stall_revenue = main_revenue
            service.sub_stall_revenue = sub_revenue
            service.total_revenue = total_revenue
            service.save(update_fields=[
                'main_stall_revenue',
                'sub_stall_revenue',
                'total_revenue',
                'updated_at'
            ])
            # Recalculate payment status whenever revenue changes
            service.update_payment_status()

        return {
            'main_revenue': main_revenue,
            'sub_revenue': sub_revenue,
            'total_revenue': total_revenue,
        }


class ServiceCompletionHandler:
    """Handles service completion workflow."""

    @staticmethod
    def complete_service(service, user=None, create_receipt=True):
        """
        Complete a service: consume reserved stock, create transactions, calculate revenue.

        Args:
            service: Service instance to complete
            user: User completing the service (for audit trail)
            create_receipt: If True, create a unified sales receipt (only if appliances exist)

        Returns:
            dict with completion details

        Raises:
            ValidationError: If service cannot be completed
        """
        from utils.enums import ServiceStatus as ServiceStatusEnum


        with transaction.atomic():
            # Validate service can be completed
            if service.status == ServiceStatusEnum.COMPLETED:
                raise ValidationError("Service is already completed.")

            # Check if service has appliances to process
            has_appliances = service.appliances.exists()

            if has_appliances:
                main_stall = get_main_stall()
                sub_stall = get_sub_stall()

                if not main_stall or not sub_stall:
                    raise ValidationError("System stalls not properly configured.")

                # Collect all charged parts for a single sub stall transaction
                parts_to_sell = []
                
                # Process each appliance item used
                for appliance in service.appliances.all():
                    for item_used in appliance.items_used.all():
                        if not item_used.stall_stock:
                            continue

                        # Consume reservation (convert reserved -> consumed)
                        StockReservationManager.consume_reservation(
                            item=item_used.item,
                            quantity=item_used.quantity,
                            stall_stock=item_used.stall_stock
                        )

                        # Calculate charged quantity (excluding free items/quantities)
                        charged_qty = item_used.quantity - item_used.free_quantity

                        if charged_qty > 0 and not item_used.is_free:
                            parts_to_sell.append({
                                'item': item_used.item,
                                'quantity': charged_qty,
                                'unit_price': item_used.item.retail_price,
                            })

                # Create ONE sub stall transaction for ALL parts (if any)
                # But only if one doesn't already exist (from payments)
                # Skip transaction creation for complementary services
                if parts_to_sell and not service.is_complementary:
                    existing_sub_transaction = None

                    # Check if service already has a linked sub transaction
                    if service.related_sub_transaction_id:
                        try:
                            candidate = service.related_sub_transaction
                            if not candidate.voided:
                                existing_sub_transaction = candidate
                        except SalesTransaction.DoesNotExist:
                            pass

                    # Fallback: look for sub transaction created alongside the main transaction
                    if not existing_sub_transaction and service.related_transaction:
                        existing_sub_transaction = SalesTransaction.objects.filter(
                            stall=sub_stall,
                            client=service.client,
                            voided=False,
                            created_at__range=(
                                service.related_transaction.created_at - timedelta(seconds=60),
                                service.related_transaction.created_at + timedelta(seconds=60)
                            )
                        ).exclude(id=service.related_transaction.id).first()

                    if not existing_sub_transaction:
                        # Create new sub stall transaction
                        sub_sales = SalesTransaction.objects.create(
                            stall=sub_stall,
                            client=service.client,
                            sales_clerk=user
                        )

                        # Add all parts to the single transaction
                        for part in parts_to_sell:
                            SalesItem.objects.create(
                                transaction=sub_sales,
                                item=part['item'],
                                quantity=part['quantity'],
                                final_price_per_unit=part['unit_price'],
                            )

                        # Link sub transaction to service
                        service.related_sub_transaction = sub_sales
                        service.save(update_fields=['related_sub_transaction'])
                    elif not service.related_sub_transaction_id:
                        service.related_sub_transaction = existing_sub_transaction
                        service.save(update_fields=['related_sub_transaction'])

            # Calculate and save revenue attribution
            revenue_data = RevenueCalculator.calculate_service_revenue(service, save=True)

            # Update service status to completed
            service.status = ServiceStatusEnum.COMPLETED
            service.save(update_fields=['status', 'updated_at'])

            # Cascade status to all appliances
            from utils.enums import ApplianceStatus
            service.appliances.exclude(
                status=ApplianceStatus.COMPLETED
            ).update(status=ApplianceStatus.COMPLETED)
            
            # Activate warranties for all appliances when service is completed
            from datetime import date
            completion_date = date.today()
            for appliance in service.appliances.all():
                if appliance.labor_warranty_months > 0 or appliance.unit_warranty_months > 0:
                    appliance.activate_warranties(start_date=completion_date)
            
            # For installation services, set warranty_start_date and mark as sold on all aircon units
            from utils.enums import ServiceType
            if service.service_type == ServiceType.INSTALLATION:
                for unit in service.installation_units.all():
                    update_fields = []
                    if not unit.warranty_start_date:
                        unit.warranty_start_date = completion_date
                        update_fields.append('warranty_start_date')
                    if not unit.is_sold:
                        unit.is_sold = True
                        unit.reserved_by = None
                        unit.reserved_at = None
                        update_fields.extend(['is_sold', 'reserved_by', 'reserved_at'])
                    if update_fields:
                        update_fields.append('updated_at')
                        unit.save(update_fields=update_fields)

            # Update payment status (sets to NOT_APPLICABLE for complementary services)
            service.update_payment_status()

            # Create separate stall transactions based on what's being charged
            # Skip if related_transaction exists (payments made upfront) or service is fully complementary
            main_receipt = None
            sub_receipt = None
            
            if create_receipt and service.client and has_appliances and not service.related_transaction and not service.is_complementary:
                main_stall = get_main_stall()
                sub_stall = get_sub_stall()
                
                # Check if there's any paid labor
                has_paid_labor = any(
                    appl.discounted_labor_fee > 0 and not appl.labor_is_free
                    for appl in service.appliances.all()
                )
                
                # Check if there's any paid parts
                has_paid_parts = any(
                    item_used.line_total > 0 and not item_used.is_free
                    for appl in service.appliances.all()
                    for item_used in appl.items_used.all()
                )
                
                # Create Main stall transaction for labor if any paid labor exists
                if has_paid_labor:
                    main_receipt = SalesTransaction.objects.create(
                        stall=main_stall,
                        client=service.client,
                        sales_clerk=user,
                    )
                    
                    for appliance in service.appliances.all():
                        labor_charge = appliance.discounted_labor_fee
                        if labor_charge > 0 and not appliance.labor_is_free:
                            SalesItem.objects.create(
                                transaction=main_receipt,
                                item=None,
                                description=f"Labor: {appliance.appliance_type.name if appliance.appliance_type else 'Service'}",
                                quantity=1,
                                final_price_per_unit=labor_charge,
                            )
                    
                    # Add aircon unit prices for installation services (Main stall revenue)
                    if service.service_type == 'installation':
                        for unit in service.installation_units.all():
                            if unit.model:
                                # Check for custom unit_price override on linked appliance
                                matching_appliance = service.appliances.filter(
                                    serial_number=unit.serial_number
                                ).first()
                                if matching_appliance and matching_appliance.unit_price:
                                    unit_final_price = matching_appliance.unit_price
                                else:
                                    unit_final_price = unit.model.selling_price
                                if unit_final_price > 0:
                                    SalesItem.objects.create(
                                        transaction=main_receipt,
                                        item=None,
                                        description=f"Aircon Unit: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                                        quantity=1,
                                        final_price_per_unit=unit_final_price,
                                    )
                    
                    # Link main receipt to service
                    service.related_transaction = main_receipt
                    service.save(update_fields=['related_transaction'])

                    # Apply service-level discount to Main stall items
                    service_discount = Decimal('0')
                    main_subtotal = main_receipt.subtotal or Decimal('0')
                    if service.service_discount_percentage and service.service_discount_percentage > 0:
                        sub_subtotal = Decimal('0')
                        # We'll compute sub_subtotal after sub receipt is created (if any)
                        # For now, estimate from revenue data
                        sub_subtotal = Decimal(str(revenue_data.get('sub_revenue', 0)))
                        combined = main_subtotal + sub_subtotal
                        service_discount = (combined * service.service_discount_percentage / Decimal('100')).quantize(
                            Decimal('0.01'), rounding=ROUND_HALF_UP
                        )
                    elif service.service_discount_amount and service.service_discount_amount > 0:
                        service_discount = service.service_discount_amount

                    if service_discount > 0 and main_subtotal > 0:
                        items = list(main_receipt.items.all())
                        remaining_discount = service_discount
                        for i, item in enumerate(items):
                            if i == len(items) - 1:
                                item_discount = remaining_discount
                            else:
                                item_discount = (service_discount * item.line_total / main_subtotal).quantize(
                                    Decimal('0.01'), rounding=ROUND_HALF_UP
                                )
                            per_unit_discount = (item_discount / item.quantity).quantize(
                                Decimal('0.01'), rounding=ROUND_HALF_UP
                            )
                            item.final_price_per_unit = max(
                                Decimal('0'),
                                item.final_price_per_unit - per_unit_discount,
                            )
                            item.save(update_fields=['final_price_per_unit'])
                            remaining_discount -= item_discount

                # Create Sub stall transaction for parts if any paid parts exist
                # Only if not already created earlier (check if one exists from the parts_to_sell logic)
                if has_paid_parts:
                    # First check linked sub transaction
                    existing_sub_transaction = None
                    if service.related_sub_transaction_id:
                        try:
                            candidate = service.related_sub_transaction
                            if not candidate.voided:
                                existing_sub_transaction = candidate
                        except SalesTransaction.DoesNotExist:
                            pass

                    # Fallback: time-window lookup
                    if not existing_sub_transaction:
                        existing_sub_transaction = SalesTransaction.objects.filter(
                            stall=sub_stall,
                            client=service.client,
                            voided=False,
                            created_at__range=(
                                timezone.now() - timedelta(seconds=60),
                                timezone.now()
                            )
                        ).first()

                    if not existing_sub_transaction:
                        sub_receipt = SalesTransaction.objects.create(
                            stall=sub_stall,
                            client=service.client,
                            sales_clerk=user,
                        )

                        for appliance in service.appliances.all():
                            for item_used in appliance.items_used.all():
                                if item_used.is_free:
                                    continue

                                charged_qty = item_used.quantity - item_used.free_quantity
                                if charged_qty > 0 and item_used.item:
                                    SalesItem.objects.create(
                                        transaction=sub_receipt,
                                        item=item_used.item,
                                        quantity=charged_qty,
                                        final_price_per_unit=item_used.item.retail_price,
                                    )

                        # Link sub receipt to service
                        service.related_sub_transaction = sub_receipt
                        service.save(update_fields=['related_sub_transaction'])
                    elif not service.related_sub_transaction_id:
                        service.related_sub_transaction = existing_sub_transaction
                        service.save(update_fields=['related_sub_transaction'])
            
            return {
                'service_id': service.id,
                'status': 'completed',
                'revenue': revenue_data,
                'receipt': (main_receipt or sub_receipt).id if (main_receipt or sub_receipt) else (service.related_transaction.id if service.related_transaction else None),
                'main_receipt': main_receipt.id if main_receipt else None,
                'sub_receipt': sub_receipt.id if sub_receipt else None,
                'message': 'Service completed without items/appliances. Add items and create invoice separately.' if not has_appliances else 'Service completed successfully.',
            }

    @staticmethod
    def _create_unified_receipt(service, user, revenue_data):
        """
        Create a unified sales receipt showing both Main and Sub revenues.
        Uses Main stall as the primary stall for the receipt.
        """
        main_stall = get_main_stall()

        receipt = SalesTransaction.objects.create(
            stall=main_stall,
            client=service.client,
            sales_clerk=user,
        )

        # Add labor charges (only if not marked as free)
        for appliance in service.appliances.all():
            labor_charge = appliance.discounted_labor_fee
            if labor_charge > 0 and not appliance.labor_is_free:
                SalesItem.objects.create(
                    transaction=receipt,
                    item=None,  # Non-inventory item
                    description=f"Labor: {appliance.appliance_type.name if appliance.appliance_type else 'Service'}",
                    quantity=1,
                    final_price_per_unit=labor_charge,
                )
        
        # Add aircon unit prices for installation services (Main stall revenue)
        if service.service_type == 'installation':
            for unit in service.installation_units.all():
                if unit.model:
                    # Check for appliance-level unit_price override
                    matching_appliance = service.appliances.filter(
                        serial_number=unit.serial_number
                    ).first()
                    if matching_appliance and matching_appliance.unit_price:
                        unit_price = matching_appliance.unit_price
                    else:
                        unit_price = unit.model.selling_price
                    if unit_price > 0:
                        SalesItem.objects.create(
                            transaction=receipt,
                            item=None,
                            description=f"Aircon Unit: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                            quantity=1,
                            final_price_per_unit=unit_price,
                        )

        # Add parts charges
        for appliance in service.appliances.all():
            for item_used in appliance.items_used.all():
                if item_used.is_free:
                    continue

                charged_qty = item_used.quantity - item_used.free_quantity
                if charged_qty > 0 and item_used.item:  # Check if item exists
                    SalesItem.objects.create(
                        transaction=receipt,
                        item=item_used.item,
                        quantity=charged_qty,
                        final_price_per_unit=item_used.item.retail_price,
                    )

        # Link receipt to service
        service.related_transaction = receipt
        service.save(update_fields=['related_transaction'])

        return receipt


class ServiceCancellationHandler:
    """Handles service cancellation workflow."""

    @staticmethod
    def cancel_service(service, reason="", user=None):
        """
        Cancel a service and release all reserved stock.

        Args:
            service: Service instance to cancel
            reason: Cancellation reason
            user: User cancelling the service

        Returns:
            dict with cancellation details
        """
        from utils.enums import ServiceStatus

        with transaction.atomic():
            released_items = []

            # Release all reserved stock
            for appliance in service.appliances.all():
                for item_used in appliance.items_used.all():
                    if item_used.stall_stock:
                        StockReservationManager.release_reservation(
                            item=item_used.item,
                            quantity=item_used.quantity,
                            stall_stock=item_used.stall_stock
                        )

                        released_items.append({
                            'item': item_used.item.name,
                            'quantity': item_used.quantity,
                        })

            # Update service status
            service.status = ServiceStatus.CANCELLED
            service.remarks = f"{service.remarks}\n\nCancellation reason: {reason}".strip()
            service.save(update_fields=['status', 'remarks', 'updated_at'])

            # Cascade status to all appliances — mark them as received (back to initial)
            from utils.enums import ApplianceStatus
            service.appliances.all().update(status=ApplianceStatus.RECEIVED)

            return {
                'service_id': service.id,
                'status': 'cancelled',
                'released_items': released_items,
            }


# Convenience functions for common operations

def reserve_service_parts(service):
    """Reserve all parts for a scheduled service."""
    reserved = []
    for appliance in service.appliances.all():
        for item_used in appliance.items_used.all():
            stock = StockReservationManager.reserve_stock(
                item=item_used.item,
                quantity=item_used.quantity,
                stall_stock=item_used.stall_stock
            )
            reserved.append({
                'item': item_used.item.name,
                'quantity': item_used.quantity,
                'stall': stock.stall.name,
            })
    return reserved


def complete_service(service, user=None):
    """Shortcut to complete a service."""
    return ServiceCompletionHandler.complete_service(service, user=user)


def cancel_service(service, reason="", user=None):
    """Shortcut to cancel a service."""
    return ServiceCancellationHandler.cancel_service(service, reason=reason, user=user)


def calculate_revenue(service):
    """Shortcut to calculate service revenue."""
    return RevenueCalculator.calculate_service_revenue(service, save=True)


# ----------------------------------
# Service Payment Manager
# ----------------------------------
class ServicePaymentManager:
    """
    Manager for service payment operations.

    Handles payment creation, validation, and status updates.
    Prevents overpayment and ensures data integrity.
    """

    @staticmethod
    def sync_sales_items(service):
        """
        Sync sales transaction items with current service charges.
        Updates line items when labor fees or unit prices change.
        
        Includes:
        - Labor fees (discounted) for each appliance
        - Aircon unit prices for installation services (brand-new & second-hand)
        
        Note: Parts are NOT synced here - they have separate sub stall transactions.
        
        Args:
            service: Service instance with related_transaction
        """
        from sales.models import SalesItem
        
        if not service.related_transaction:
            return
            
        sales_transaction = service.related_transaction
        
        # Clear existing items and recreate
        sales_transaction.items.all().delete()
        
        # Pre-build set of installation unit serial numbers
        installation_unit_serials = set()
        if service.service_type == 'installation':
            installation_unit_serials = set(
                service.installation_units.values_list('serial_number', flat=True)
            )
        
        # Add labor fees for each appliance (use discounted fee)
        for appliance in service.appliances.all():
            labor_charge = appliance.discounted_labor_fee or Decimal('0.00')
            if labor_charge > 0 and not appliance.labor_is_free:
                appliance_name = appliance.appliance_type.name if appliance.appliance_type else "Appliance"
                brand_info = f" ({appliance.brand})" if appliance.brand else ""
                SalesItem.objects.create(
                    transaction=sales_transaction,
                    item=None,
                    description=f"Labor Fee - {appliance_name}{brand_info}",
                    quantity=1,
                    final_price_per_unit=labor_charge,
                )
            # Add unit_price for second-hand / non-installation appliances
            if appliance.unit_price and appliance.serial_number not in installation_unit_serials:
                SalesItem.objects.create(
                    transaction=sales_transaction,
                    item=None,
                    description=f"Unit: {appliance.brand or ''} {appliance.model or ''} (Second-hand)",
                    quantity=1,
                    final_price_per_unit=appliance.unit_price,
                )
        
        # Add aircon unit prices for installation services (Main stall revenue)
        if service.service_type == 'installation':
            for unit in service.installation_units.all():
                if unit.model:
                    # Check for custom unit_price override on linked appliance
                    matching_appliance = service.appliances.filter(
                        serial_number=unit.serial_number
                    ).first()
                    if matching_appliance and matching_appliance.unit_price:
                        unit_final_price = matching_appliance.unit_price
                    else:
                        unit_final_price = unit.model.selling_price
                    if unit_final_price > 0:
                        SalesItem.objects.create(
                            transaction=sales_transaction,
                            item=None,
                            description=f"Aircon Unit: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                            quantity=1,
                            final_price_per_unit=unit_final_price,
                        )
        
        # Apply service-level discount to Main stall items only
        service_discount = Decimal('0.00')
        main_subtotal = sales_transaction.subtotal or Decimal('0.00')
        if service.service_discount_percentage and service.service_discount_percentage > 0:
            sub_tx = service.related_sub_transaction
            sub_subtotal = (sub_tx.subtotal or Decimal('0.00')) if sub_tx else Decimal('0.00')
            combined = main_subtotal + sub_subtotal
            service_discount = (combined * service.service_discount_percentage / Decimal('100')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        elif service.service_discount_amount and service.service_discount_amount > 0:
            service_discount = service.service_discount_amount

        if service_discount > 0 and main_subtotal > 0:
            items = list(sales_transaction.items.all())
            remaining_discount = service_discount
            for i, item in enumerate(items):
                if i == len(items) - 1:
                    item_discount = remaining_discount
                else:
                    item_discount = (service_discount * item.line_total / main_subtotal).quantize(
                        Decimal('0.01'), rounding=ROUND_HALF_UP
                    )
                per_unit_discount = (item_discount / item.quantity).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )
                item.final_price_per_unit = max(
                    Decimal('0'),
                    item.final_price_per_unit - per_unit_discount,
                )
                item.save(update_fields=['final_price_per_unit'])
                remaining_discount -= item_discount

        # Update payment status after syncing items
        sales_transaction.update_payment_status()

    @staticmethod
    def recreate_sales_transaction(service):
        """
        Recreate sales transaction from existing service payments.
        Use this when a sales transaction is deleted but service payments exist.
        
        Args:
            service: Service instance
            
        Returns:
            Created SalesTransaction or None
        """
        from sales.models import SalesItem, SalesPayment, SalesTransaction
        
        # Check if service has payments but no transaction
        service_payments = service.payments.all()
        if not service_payments.exists():
            return None
        
        with transaction.atomic():
            # Get system stalls
            main_stall = get_main_stall()
            sub_stall = get_sub_stall()
            
            # Create new main stall sales transaction for labor fees
            sales_transaction = SalesTransaction.objects.create(
                stall=service.stall or main_stall,
                client=service.client,
                sales_clerk=service_payments.first().received_by if service_payments.first().received_by else None,
            )
            service.related_transaction = sales_transaction
            service.save(update_fields=["related_transaction"])
            
            # Create sales items for labor fees (main stall)
            for appliance in service.appliances.all():
                if appliance.labor_fee > 0 and not appliance.labor_is_free:
                    appliance_name = appliance.appliance_type.name if appliance.appliance_type else "Appliance"
                    brand_info = f" ({appliance.brand})" if appliance.brand else ""
                    SalesItem.objects.create(
                        transaction=sales_transaction,
                        item=None,
                        description=f"Labor Fee - {appliance_name}{brand_info}",
                        quantity=1,
                        final_price_per_unit=appliance.labor_fee,
                    )
            
            # Add aircon unit prices for installation services (Main stall revenue)
            if service.service_type == 'installation':
                for unit in service.installation_units.all():
                    if unit.model:
                        # Check for appliance-level unit_price override
                        matching_appliance = service.appliances.filter(
                            serial_number=unit.serial_number
                        ).first()
                        if matching_appliance and matching_appliance.unit_price:
                            unit_price = matching_appliance.unit_price
                        else:
                            unit_price = unit.model.selling_price
                        if unit_price > 0:
                            SalesItem.objects.create(
                                transaction=sales_transaction,
                                item=None,
                                description=f"Aircon Unit: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                                quantity=1,
                                final_price_per_unit=unit_price,
                            )
            
            # Collect all parts from all appliances
            parts_to_add = []
            for appliance in service.appliances.all():
                for item_used in appliance.items_used.all():
                    # Skip free items
                    if item_used.is_free:
                        continue
                        
                    charged_qty = item_used.quantity - item_used.free_quantity
                    if charged_qty > 0 and item_used.item:
                        parts_to_add.append({
                            'item': item_used.item,
                            'quantity': charged_qty,
                        })
            
            # Create ONE sub stall transaction for ALL parts (if any)
            sub_sales_transaction = None
            if parts_to_add:
                sub_sales_transaction = SalesTransaction.objects.create(
                    stall=sub_stall,
                    client=service.client,
                    sales_clerk=service_payments.first().received_by if service_payments.first().received_by else None,
                )
                
                # Add all parts to the single sub stall transaction
                for part in parts_to_add:
                    SalesItem.objects.create(
                        transaction=sub_sales_transaction,
                        item=part['item'],
                        description=part['item'].name,
                        quantity=part['quantity'],
                        final_price_per_unit=part['item'].retail_price,
                    )

                service.related_sub_transaction = sub_sales_transaction
                service.save(update_fields=["related_sub_transaction"])

            # Waterfall-allocate payments: fill main first, then sub
            main_total = sales_transaction.computed_total or Decimal("0")
            sub_total = (sub_sales_transaction.computed_total or Decimal("0")) if sub_sales_transaction else Decimal("0")
            main_filled = Decimal("0")
            sub_filled = Decimal("0")

            for service_payment in service_payments:
                m_share, s_share = ServicePaymentManager._waterfall_split(
                    service_payment.amount,
                    main_total - main_filled,
                    sub_total - sub_filled,
                )
                SalesPayment.objects.create(
                    transaction=sales_transaction,
                    payment_type=service_payment.payment_type,
                    amount=m_share,
                    payment_date=service_payment.payment_date,
                )
                if s_share > 0 and sub_sales_transaction:
                    SalesPayment.objects.create(
                        transaction=sub_sales_transaction,
                        payment_type=service_payment.payment_type,
                        amount=s_share,
                        payment_date=service_payment.payment_date,
                    )
                main_filled += m_share
                sub_filled += s_share
        
        return sales_transaction

    @staticmethod
    def create_payment(service, payment_type, amount, received_by=None, notes="", cheque_collection=None):
        """
        Create a payment for a service.

        Args:
            service: Service instance
            payment_type: Payment type (cash, gcash, etc.)
            amount: Payment amount (Decimal)
            received_by: User who received the payment (optional)
            notes: Additional notes (optional)
            cheque_collection: ChequeCollection instance (optional, for cheque payments)

        Returns:
            ServicePayment instance

        Raises:
            ValidationError: If payment would cause overpayment or invalid amount
        """
        from sales.models import SalesItem, SalesPayment, SalesTransaction
        from services.models import ServicePayment

        # Validate amount
        if amount <= 0:
            raise ValidationError("Payment amount must be greater than zero.")

        # Check for overpayment using balance_due property (accounts for refunds)
        balance_due = service.balance_due

        if amount > balance_due:
            raise ValidationError(
                f"Payment amount (₱{amount}) exceeds balance due (₱{balance_due}). "
                f"Total revenue: ₱{service.total_revenue}, Already paid: ₱{service.total_paid}"
            )

        # Create payment
        with transaction.atomic():
            payment = ServicePayment.objects.create(
                service=service,
                payment_type=payment_type,
                amount=amount,
                received_by=received_by,
                notes=notes,
                cheque_collection=cheque_collection,
            )
            # Payment status is automatically updated by the model's save() method

            # Create or update sales transactions
            # Check if related_transaction exists and is valid (not deleted)
            sales_transaction = None
            if service.related_transaction:
                try:
                    # Try to access the transaction to see if it still exists
                    sales_transaction = service.related_transaction
                    if sales_transaction.voided:
                        # Don't use voided transactions
                        sales_transaction = None
                        service.related_transaction = None
                except SalesTransaction.DoesNotExist:
                    # Transaction was deleted, clear the reference
                    service.related_transaction = None
                    sales_transaction = None
            
            # Get system stalls
            main_stall = get_main_stall()
            sub_stall = get_sub_stall()
            sub_sales_tx = None

            if not sales_transaction:
                # Create new main stall sales transaction for this service
                target_stall = service.stall if service.stall else main_stall
                sales_transaction = SalesTransaction.objects.create(
                    stall=target_stall,
                    client=service.client,
                    sales_clerk=received_by,
                )
                service.related_transaction = sales_transaction

                # Create sales items for all appliances' labor fees (MAIN STALL)
                for appliance in service.appliances.all():
                    if appliance.labor_fee > 0 and not appliance.labor_is_free:
                        appliance_name = appliance.appliance_type.name if appliance.appliance_type else "Appliance"
                        brand_info = f" ({appliance.brand})" if appliance.brand else ""
                        SalesItem.objects.create(
                            transaction=sales_transaction,
                            item=None,
                            description=f"Labor Fee - {appliance_name}{brand_info}",
                            quantity=1,
                            final_price_per_unit=appliance.labor_fee,
                        )

                # Add aircon unit prices for installation services (Main stall revenue)
                if service.service_type == 'installation':
                    for unit in service.installation_units.all():
                        if unit.model:
                            # Check for appliance-level unit_price override
                            matching_appliance = service.appliances.filter(
                                serial_number=unit.serial_number
                            ).first()
                            if matching_appliance and matching_appliance.unit_price:
                                unit_price = matching_appliance.unit_price
                            else:
                                unit_price = unit.model.selling_price
                            if unit_price > 0:
                                SalesItem.objects.create(
                                    transaction=sales_transaction,
                                    item=None,
                                    description=f"Aircon Unit: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                                    quantity=1,
                                    final_price_per_unit=unit_price,
                                )

                # Collect all parts from all appliances
                parts_to_add = []
                for appliance in service.appliances.all():
                    for item_used in appliance.items_used.all():
                        # Skip free items
                        if item_used.is_free:
                            continue

                        charged_qty = item_used.quantity - item_used.free_quantity
                        if charged_qty > 0 and item_used.item:
                            parts_to_add.append({
                                'item': item_used.item,
                                'quantity': charged_qty,
                            })

                # Find or create sub stall transaction for parts
                if parts_to_add:
                    # Check if service already has a linked sub transaction
                    if service.related_sub_transaction_id:
                        try:
                            existing = service.related_sub_transaction
                            if not existing.voided:
                                sub_sales_tx = existing
                        except SalesTransaction.DoesNotExist:
                            pass

                    # Fallback: time-window lookup for transactions from complete_service
                    if not sub_sales_tx:
                        sub_sales_tx = SalesTransaction.objects.filter(
                            stall=sub_stall,
                            client=service.client,
                            created_at__range=(
                                sales_transaction.created_at - timedelta(seconds=60),
                                sales_transaction.created_at + timedelta(seconds=60)
                            ),
                            voided=False,
                        ).exclude(id=sales_transaction.id).first()

                    # If no existing transaction, create ONE for ALL parts
                    if not sub_sales_tx:
                        sub_sales_tx = SalesTransaction.objects.create(
                            stall=sub_stall,
                            client=service.client,
                            sales_clerk=received_by,
                        )

                        # Add all parts to the single sub stall transaction
                        for part in parts_to_add:
                            SalesItem.objects.create(
                                transaction=sub_sales_tx,
                                item=part['item'],
                                description=part['item'].name,
                                quantity=part['quantity'],
                                final_price_per_unit=part['item'].retail_price,
                            )

                # Link sub transaction to service
                if sub_sales_tx:
                    service.related_sub_transaction = sub_sales_tx

                service.save(update_fields=["related_transaction", "related_sub_transaction"])

                # Apply service-level discount to Main stall SalesTransaction only
                # Service-level discounts reduce labor/service fees, not parts
                service_discount = Decimal("0")
                if service.service_discount_percentage and service.service_discount_percentage > 0:
                    main_subtotal = sales_transaction.subtotal or Decimal("0")
                    sub_subtotal = (sub_sales_tx.subtotal or Decimal("0")) if sub_sales_tx else Decimal("0")
                    combined = main_subtotal + sub_subtotal
                    service_discount = (combined * service.service_discount_percentage / Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                elif service.service_discount_amount and service.service_discount_amount > 0:
                    service_discount = service.service_discount_amount

                if service_discount > 0:
                    main_subtotal = sales_transaction.subtotal or Decimal("0")
                    if main_subtotal > 0:
                        # Spread discount across main stall items (labor fees)
                        items = list(sales_transaction.items.all())
                        remaining_discount = service_discount
                        for i, item in enumerate(items):
                            if i == len(items) - 1:
                                item_discount = remaining_discount
                            else:
                                item_discount = (service_discount * item.line_total / main_subtotal).quantize(
                                    Decimal("0.01"), rounding=ROUND_HALF_UP
                                )
                            per_unit_discount = (item_discount / item.quantity).quantize(
                                Decimal("0.01"), rounding=ROUND_HALF_UP
                            )
                            item.final_price_per_unit = max(
                                Decimal("0"),
                                item.final_price_per_unit - per_unit_discount
                            )
                            item.save(update_fields=["final_price_per_unit"])
                            remaining_discount -= item_discount

                # Waterfall-allocate previous service payments to main then sub
                main_total = sales_transaction.computed_total or Decimal("0")
                sub_total = (sub_sales_tx.computed_total or Decimal("0")) if sub_sales_tx else Decimal("0")

                previous_payments = service.payments.exclude(id=payment.id).order_by('payment_date')
                main_filled = Decimal("0")
                sub_filled = Decimal("0")

                for service_payment in previous_payments:
                    m_share, s_share = ServicePaymentManager._waterfall_split(
                        service_payment.amount,
                        main_total - main_filled,
                        sub_total - sub_filled,
                    )
                    SalesPayment.objects.create(
                        transaction=sales_transaction,
                        payment_type=service_payment.payment_type,
                        amount=m_share,
                        payment_date=service_payment.payment_date,
                    )
                    if s_share > 0 and sub_sales_tx:
                        SalesPayment.objects.create(
                            transaction=sub_sales_tx,
                            payment_type=service_payment.payment_type,
                            amount=s_share,
                            payment_date=service_payment.payment_date,
                        )
                    main_filled += m_share
                    sub_filled += s_share
            else:
                # Reuse existing transaction — find associated sub stall transaction
                if service.related_sub_transaction_id:
                    try:
                        existing = service.related_sub_transaction
                        if not existing.voided:
                            sub_sales_tx = existing
                    except SalesTransaction.DoesNotExist:
                        pass

                if not sub_sales_tx:
                    # Fallback 1: time-window lookup (±60 seconds around main TX)
                    sub_sales_tx = SalesTransaction.objects.filter(
                        stall=sub_stall,
                        client=service.client,
                        created_at__range=(
                            sales_transaction.created_at - timedelta(seconds=60),
                            sales_transaction.created_at + timedelta(seconds=60)
                        ),
                        voided=False,
                    ).exclude(id=sales_transaction.id).first()

                if not sub_sales_tx:
                    # Fallback 2: same-day lookup for sub stall TX created on
                    # the same date as the main TX (handles services completed
                    # before related_sub_transaction field existed)
                    main_date = sales_transaction.created_at.date()
                    sub_sales_tx = SalesTransaction.objects.filter(
                        stall=sub_stall,
                        client=service.client,
                        created_at__date=main_date,
                        voided=False,
                    ).exclude(id=sales_transaction.id).first()

                # Persist the link if found via fallback
                if sub_sales_tx and not service.related_sub_transaction_id:
                    service.related_sub_transaction = sub_sales_tx
                    service.save(update_fields=["related_sub_transaction"])

            # Waterfall-allocate current payment: fill main first, then sub
            main_total = sales_transaction.computed_total or Decimal("0")
            sub_total = (sub_sales_tx.computed_total or Decimal("0")) if sub_sales_tx else Decimal("0")
            main_paid = sum(p.amount for p in sales_transaction.payments.all())
            sub_paid = sum(p.amount for p in sub_sales_tx.payments.all()) if sub_sales_tx else Decimal("0")

            m_share, s_share = ServicePaymentManager._waterfall_split(
                amount,
                main_total - main_paid,
                sub_total - sub_paid,
            )

            SalesPayment.objects.create(
                transaction=sales_transaction,
                payment_type=payment_type,
                amount=m_share,
            )
            if s_share > 0 and sub_sales_tx:
                SalesPayment.objects.create(
                    transaction=sub_sales_tx,
                    payment_type=payment_type,
                    amount=s_share,
                )

        return payment

    @staticmethod
    def _waterfall_split(amount, main_remaining, sub_remaining):
        """Split a payment using waterfall: fill sub first, then main, overpayment to main."""
        s = min(amount, max(sub_remaining, Decimal("0")))
        m = min(amount - s, max(main_remaining, Decimal("0")))
        m += amount - m - s  # overpayment goes to main as change
        return m, s

    @staticmethod
    def get_outstanding_services(stall=None):
        """
        Get services with outstanding balances (unpaid or partial).

        Args:
            stall: Optional stall to filter by

        Returns:
            QuerySet of Service instances
        """
        from services.models import PaymentStatus, Service

        qs = Service.objects.filter(
            payment_status__in=[PaymentStatus.UNPAID, PaymentStatus.PARTIAL]
        )

        if stall:
            qs = qs.filter(stall=stall)

        return qs.order_by('-created_at')

    @staticmethod
    def get_payment_summary(service):
        """
        Get a payment summary for a service.

        Args:
            service: Service instance

        Returns:
            dict with payment details
        """
        return {
            'service_id': service.id,
            'total_revenue': float(service.total_revenue),
            'total_paid': float(service.total_paid),
            'balance_due': float(service.balance_due),
            'payment_status': service.payment_status,
            'payments': [
                {
                    'id': p.id,
                    'payment_type': p.payment_type,
                    'amount': float(p.amount),
                    'payment_date': p.payment_date.isoformat(),
                    'received_by': p.received_by.get_full_name() if p.received_by else None,
                    'notes': p.notes,
                }
                for p in service.payments.all()
            ],
        }

    @staticmethod
    def void_payment(payment, reason=""):
        """
        Void/delete a payment and update service payment status.

        Args:
            payment: ServicePayment instance
            reason: Reason for voiding (optional)

        Returns:
            Service instance (after update)
        """
        with transaction.atomic():
            service = payment.service
            payment.delete()
            # Payment status is automatically updated by the model's delete signal
            service.update_payment_status()
            service.refresh_from_db()

        return service


    @staticmethod
    def cancel_service(service, reason=""):
        """
        Cancel an incomplete service and return unused parts to stock.
        Only use this for services that are NOT completed.
        
        Args:
            service: Service instance to cancel
            reason: Reason for cancellation
        
        Returns:
            dict with cancellation summary
        
        Raises:
            ValidationError: If service is already completed
        """
        from django.utils import timezone
        from sales.models import SalesTransaction
        from services.models import ServiceStatus
        
        # Prevent cancelling completed services (use refund instead)
        if service.status == ServiceStatus.COMPLETED:
            raise ValidationError(
                "Cannot cancel a completed service. Use refund_service() instead."
            )
        
        with transaction.atomic():
            # 1. Mark service as cancelled
            original_status = service.status
            service.status = ServiceStatus.CANCELLED
            service.cancellation_reason = reason
            service.cancellation_date = timezone.now()
            service.save(update_fields=["status", "cancellation_reason", "cancellation_date"])
            
            # 2. Return parts to stock (parts NOT used yet)
            parts_returned = 0
            for appliance in service.appliances.all():
                for item_used in appliance.items_used.all():
                    if item_used.stall_stock:
                        # Return quantity to stock
                        item_used.stall_stock.quantity += item_used.quantity
                        # Release reservation if any
                        if item_used.stall_stock.reserved_quantity >= item_used.quantity:
                            item_used.stall_stock.reserved_quantity -= item_used.quantity
                        item_used.stall_stock.save()
                        parts_returned += 1
                        
                        # Mark item_used as cancelled
                        item_used.is_cancelled = True
                        item_used.cancelled_at = timezone.now()
                        item_used.save(update_fields=["is_cancelled", "cancelled_at"])
            
            # 3. Void sales transactions
            transactions_voided = 0
            if service.related_transaction:
                service.related_transaction.voided = True
                service.related_transaction.voided_at = timezone.now()
                service.related_transaction.void_reason = f"Service cancelled: {reason}"
                service.related_transaction.save(update_fields=["voided", "voided_at", "void_reason"])
                transactions_voided += 1
            
            # Find and void sub stall transaction
            sub_stall = get_sub_stall()
            sub_transaction = SalesTransaction.objects.filter(
                stall=sub_stall,
                client=service.client,
                created_at__gte=service.created_at,
            ).first()
            
            if sub_transaction:
                sub_transaction.voided = True
                sub_transaction.voided_at = timezone.now()
                sub_transaction.void_reason = f"Service cancelled: {reason}"
                sub_transaction.save(update_fields=["voided", "voided_at", "void_reason"])
                transactions_voided += 1
            
            # 4. Calculate refund amount (if payments were made)
            refund_amount = service.total_paid
            
            return {
                'service_id': service.id,
                'original_status': original_status,
                'parts_returned_to_stock': parts_returned,
                'transactions_voided': transactions_voided,
                'refund_due': float(refund_amount),
            }
    
    @staticmethod
    def refund_service(service, refund_amount, reason="", refund_type="full", refund_method="cash", processed_by=None):
        """
        Process refund for a COMPLETED service where parts are already used.
        Parts are NOT returned to stock.
        
        Args:
            service: Service instance (must be completed)
            refund_amount: Amount to refund (Decimal)
            reason: Reason for refund (e.g., "Customer dissatisfaction", "Warranty issue")
            refund_type: "full" or "partial"
            refund_method: "cash", "gcash", or "bank_transfer"
            processed_by: User processing the refund (optional)
        
        Returns:
            dict with refund details
        
        Raises:
            ValidationError: If service is not completed or refund invalid
        """
        from django.utils import timezone
        from services.models import ServiceRefund, ServiceStatus
        
        # Only allow refunds for completed services
        if service.status != ServiceStatus.COMPLETED:
            raise ValidationError(
                "Can only process refunds for completed services. "
                "Use cancel_service() for incomplete services."
            )
        
        # Validate refund amount
        refund_amount = Decimal(str(refund_amount))
        if refund_amount <= 0:
            raise ValidationError("Refund amount must be greater than zero")
        
        if refund_amount > service.total_paid:
            raise ValidationError(
                f"Refund amount (₱{refund_amount}) cannot exceed total paid (₱{service.total_paid})"
            )
        
        with transaction.atomic():
            # Create refund record
            refund = ServiceRefund.objects.create(
                service=service,
                refund_amount=refund_amount,
                refund_type=refund_type,
                reason=reason,
                refund_method=refund_method,
                processed_by=processed_by,
            )
            
            # Update service refund tracking
            service.total_refunded = (service.total_refunded or 0) + refund_amount
            service.last_refund_date = timezone.now()
            service.save(update_fields=['total_refunded', 'last_refund_date'])
            
            # Update payment status to reflect refund
            service.update_payment_status()
            
            # DO NOT return parts to stock (already used)
            # DO NOT void sales transactions (costs already incurred)
            
            return {
                'refund_id': refund.id,
                'service_id': service.id,
                'refund_amount': float(refund_amount),
                'refund_type': refund_type,
                'total_refunded': float(service.total_refunded),
                'net_revenue': float(service.net_revenue),
                'parts_returned_to_stock': 0,  # None - parts already used
            }


def create_service_payment(service, payment_type, amount, received_by=None, notes=""):
    """Shortcut to create a service payment."""
    return ServicePaymentManager.create_payment(
        service=service,
        payment_type=payment_type,
        amount=amount,
        received_by=received_by,
        notes=notes,
    )
