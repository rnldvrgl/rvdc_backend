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
from sales.models import SalesItem, SalesTransaction, TransactionType, DocumentType


def get_main_stall():
    """Get the Main stall (services + aircon units)."""
    return Stall.objects.filter(stall_type='main', is_system=True).first()


def get_sub_stall():
    """Get the Sub stall (parts inventory)."""
    return Stall.objects.filter(stall_type='sub', is_system=True).first()


def get_sub_stall_unit_revenue_additional():
    """Get configured additional unit allocation shifted from main to sub stall."""
    from users.models import SystemSettings

    try:
        settings_obj = SystemSettings.get_settings()
        configured = settings_obj.sub_stall_unit_revenue_additional or Decimal('0.00')
    except Exception:
        configured = Decimal('0.00')

    try:
        value = Decimal(str(configured))
    except Exception:
        value = Decimal('0.00')

    return max(value, Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def get_installation_unit_revenue_split(service, unit):
    """
    Return per-unit split between main and sub stalls.

    Rules:
    - Base split: sub gets unit cost, main gets margin (selling - cost)
    - Additional configured amount is shifted from main margin to sub
    """
    if not unit.model:
        return Decimal('0.00'), Decimal('0.00')

    matching_appliance = service.appliances.filter(
        serial_number=unit.serial_number
    ).first()

    if matching_appliance and matching_appliance.unit_price:
        selling_price = matching_appliance.unit_price
    else:
        selling_price = unit.model.selling_price or Decimal('0.00')

    cost_price = unit.model.cost_price or Decimal('0.00')
    margin = max(selling_price - cost_price, Decimal('0.00'))

    additional_shift = min(get_sub_stall_unit_revenue_additional(), margin)
    main_revenue = margin - additional_shift
    sub_revenue = cost_price + additional_shift

    return main_revenue, sub_revenue


class StockReservationManager:
    """Manages stock reservations for service parts."""

    @staticmethod
    def reserve_stock(item, quantity, stall_stock=None):
        """
        Reserve stock for a service part.

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

            if available < quantity_dec:
                raise ValidationError(
                    f"Insufficient stock for {item.name}. "
                    f"Available: {available}, Requested: {quantity}"
                )

            stall_stock.reserved_quantity += quantity_dec
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

            if quantity_dec > stock.reserved_quantity:
                raise ValidationError(
                    f"Cannot consume {quantity} of {item.name}: only "
                    f"{stock.reserved_quantity} reserved."
                )

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

        # Auto-adjust labor fees for appliances with auto_adjust_labor enabled
        for appliance in service.appliances.all():
            if appliance.auto_adjust_labor and appliance.total_service_fee is not None:
                parts_cost = sum(
                    (item.line_total for item in appliance.items_used.all()),
                    Decimal('0.00'),
                )
                new_labor = max(appliance.total_service_fee - parts_cost, Decimal('0.00'))
                if new_labor != appliance.labor_fee:
                    appliance.labor_fee = new_labor
                    appliance.save(update_fields=['labor_fee'])

        # Pre-build set of installation unit serial numbers
        # so we don't double-count brand_new unit prices
        installation_unit_serials = set()
        if service.service_type == 'installation':
            installation_unit_serials = set(
                service.installation_units.values_list('serial_number', flat=True)
            )

        # Calculate labor fees (Main stall revenue) with discounts.
        # Installation services use the per-unit split helper for main share,
        # so appliance labor rows must not be added to main revenue.
        for appliance in service.appliances.all():
            if service.service_type != 'installation':
                # Use discounted_labor_fee which accounts for labor discounts
                main_revenue += appliance.discounted_labor_fee or Decimal('0.00')

            # Use discounted_labor_fee which accounts for labor discounts
            # Add unit_price only for non-installation appliances.
            # Installation units are handled in the installation_units split loop below.
            if service.service_type != 'installation' and appliance.unit_price:
                main_revenue += appliance.unit_price

        # Add aircon unit prices for installation services
        # Split: cost_price → sub stall, (selling_price - cost_price) → main stall
        if service.service_type == 'installation':
            for unit in service.installation_units.all():
                unit_main_revenue, unit_sub_revenue = get_installation_unit_revenue_split(service, unit)
                sub_revenue += unit_sub_revenue
                main_revenue += unit_main_revenue

        # Calculate parts revenue (Sub stall revenue) with discounts
        for appliance in service.appliances.all():
            for item_used in appliance.items_used.all():
                # Use line_total which already accounts for discounts and free quantities
                sub_revenue += item_used.line_total

        # Include service-level items (not tied to any appliance)
        for item_used in service.service_items.all():
            sub_revenue += item_used.line_total

        # Include extra charges (e.g. dismantle fee, site survey)
        extra_charges_total = sum(
            Decimal(str(ec.amount)) for ec in service.extra_charges.all()
        )
        main_revenue += extra_charges_total

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
            # Re-fetch with row lock to prevent concurrent completion/cancellation
            from services.models import Service as ServiceModel
            service = ServiceModel.objects.select_for_update().get(pk=service.pk)

            # Validate service can be completed
            if service.status == ServiceStatusEnum.COMPLETED:
                raise ValidationError("Service is already completed.")

            # Check if service has appliances to process
            has_appliances = service.appliances.exists()
            has_service_items = service.service_items.exists()

            if has_appliances or has_service_items:
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
                                'unit_price': item_used.discounted_price,
                            })

                    # Also include custom items (no stock, but billable)
                    for item_used in appliance.items_used.filter(item__isnull=True, custom_price__isnull=False):
                        if not item_used.is_free and item_used.line_total > 0:
                            charged_qty = item_used.quantity - item_used.free_quantity
                            if charged_qty > 0:
                                parts_to_sell.append({
                                    'item': None,
                                    'description': 'Custom Item',
                                    'quantity': charged_qty,
                                    'unit_price': item_used.discounted_price,
                                })

                # Process service-level items (chipping/pre-installation)
                for item_used in service.service_items.all():
                    if not item_used.stall_stock:
                        # Still include custom items that have no stock
                        if item_used.is_custom_item and not item_used.is_free and item_used.line_total > 0:
                            charged_qty = item_used.quantity - item_used.free_quantity
                            if charged_qty > 0:
                                parts_to_sell.append({
                                    'item': None,
                                    'description': 'Custom Item',
                                    'quantity': charged_qty,
                                    'unit_price': item_used.discounted_price,
                                })
                        continue

                    StockReservationManager.consume_reservation(
                        item=item_used.item,
                        quantity=item_used.quantity,
                        stall_stock=item_used.stall_stock
                    )

                    charged_qty = item_used.quantity - item_used.free_quantity

                    if charged_qty > 0 and not item_used.is_free:
                        parts_to_sell.append({
                            'item': item_used.item,
                            'quantity': charged_qty,
                            'unit_price': item_used.discounted_price,
                        })

                # Build installation unit allocation lines for sub stall
                sub_unit_items = []
                if service.service_type == 'installation':
                    for unit in service.installation_units.all():
                        if unit.model:
                            _, unit_sub_revenue = get_installation_unit_revenue_split(service, unit)
                        else:
                            unit_sub_revenue = Decimal('0.00')

                        if unit_sub_revenue > 0:
                            sub_unit_items.append({
                                'description': f"Aircon Unit Cost: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                                'price': unit_sub_revenue,
                            })

                # Create ONE sub stall transaction for ALL parts/unit allocations (if any)
                # But only if one doesn't already exist (from payments)
                # Skip transaction creation for complementary services
                if (parts_to_sell or sub_unit_items) and not service.is_complementary:
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
                            sales_clerk=user,
                            transaction_type=TransactionType.SERVICE,
                            document_type=DocumentType.SALES_INVOICE,
                            with_2307=False,
                        )

                        # Add all parts to the single transaction
                        for part in parts_to_sell:
                            SalesItem.objects.create(
                                transaction=sub_sales,
                                item=part['item'],
                                description=part.get('description', ''),
                                quantity=part['quantity'],
                                final_price_per_unit=part['unit_price'],
                            )

                        for unit_item in sub_unit_items:
                            SalesItem.objects.create(
                                transaction=sub_sales,
                                item=None,
                                description=unit_item['description'],
                                quantity=1,
                                final_price_per_unit=unit_item['price'],
                            )

                        # Link sub transaction to service
                        service.related_sub_transaction = sub_sales
                        service.save(update_fields=['related_sub_transaction'])
                    elif not service.related_sub_transaction_id:
                        service.related_sub_transaction = existing_sub_transaction
                        service.save(update_fields=['related_sub_transaction'])

            # Calculate and save revenue attribution
            revenue_data = RevenueCalculator.calculate_service_revenue(service, save=True)

            # Auto-mark as complementary if total revenue is zero
            if not service.is_complementary and revenue_data.get('total_revenue', 0) <= 0:
                service.is_complementary = True
                service.save(update_fields=['is_complementary', 'updated_at'])

            # Update service status to completed
            service.status = ServiceStatusEnum.COMPLETED
            service.save(update_fields=['status', 'updated_at'])

            # Cascade status to all appliances
            from utils.enums import ApplianceStatus
            service.appliances.exclude(
                status=ApplianceStatus.COMPLETED
            ).update(status=ApplianceStatus.COMPLETED)

            # Activate warranties for all appliances when service is completed
            # Skip warranty activation for complementary services (warranty claims / free cleaning)
            # to prevent warranty-on-warranty chains
            from datetime import date
            completion_date = date.today()
            if not service.is_complementary:
                for appliance in service.appliances.all():
                    if appliance.labor_warranty_months > 0 or appliance.unit_warranty_months > 0:
                        appliance.activate_warranties(start_date=completion_date)

            # Auto-claim all unclaimed, non-forfeited appliances when the service is completed.
            # Applies to carry_in and pull_out modes where the customer physically collects their unit.
            from utils.enums import ServiceMode
            now = timezone.now()
            if service.service_mode in (ServiceMode.CARRY_IN, ServiceMode.PULL_OUT):
                service.appliances.filter(
                    claimed_at__isnull=True,
                    is_forfeited=False,
                ).update(claimed_at=now)
                # Mark the service itself as claimed if all appliances are now resolved
                if not service.appliances.filter(claimed_at__isnull=True, is_forfeited=False).exists():
                    service.claimed_at = now
                    service.save(update_fields=['claimed_at', 'updated_at'])

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

            if create_receipt and service.client and (has_appliances or has_service_items) and not service.related_transaction and not service.is_complementary:
                main_stall = get_main_stall()
                sub_stall = get_sub_stall()

                # Installation main share is represented via unit split lines,
                # not appliance labor rows.
                has_paid_labor = (
                    service.service_type != 'installation'
                    and any(
                        appl.discounted_labor_fee > 0 and not appl.labor_is_free
                        for appl in service.appliances.all()
                    )
                )

                # Check if there's any paid parts (appliance-level + service-level)
                has_paid_parts = any(
                    item_used.line_total > 0 and not item_used.is_free
                    for appl in service.appliances.all()
                    for item_used in appl.items_used.all()
                ) or any(
                    item_used.line_total > 0 and not item_used.is_free
                    for item_used in service.service_items.all()
                )

                # Create Main stall transaction for labor if any paid labor exists
                if has_paid_labor:
                    main_receipt = SalesTransaction.objects.create(
                        stall=main_stall,
                        client=service.client,
                        sales_clerk=user,
                        transaction_type=TransactionType.SERVICE,
                        document_type=DocumentType.OFFICIAL_RECEIPT,
                        with_2307=getattr(service, 'with_2307', False),
                    )

                    if service.service_type != 'installation':
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

                    # Add aircon unit prices for installation services
                    if service.service_type == 'installation':
                        for unit in service.installation_units.all():
                            if unit.model:
                                unit_final_price, _ = get_installation_unit_revenue_split(service, unit)
                            else:
                                unit_final_price = Decimal('0.00')

                            if unit_final_price > 0:
                                SalesItem.objects.create(
                                    transaction=main_receipt,
                                    item=None,
                                    description=f"Aircon Unit: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                                    quantity=1,
                                    final_price_per_unit=unit_final_price,
                                )

                    # Add extra charges (e.g. special bracket, hauling fee)
                    for ec in service.extra_charges.all():
                        ec_amount = Decimal(str(ec.amount))
                        if ec_amount > 0:
                            SalesItem.objects.create(
                                transaction=main_receipt,
                                item=None,
                                description=ec.name,
                                quantity=1,
                                final_price_per_unit=ec_amount,
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

                # Build installation unit allocation lines for sub stall
                sub_unit_items = []
                if service.service_type == 'installation':
                    for unit in service.installation_units.all():
                        if unit.model:
                            _, unit_sub_revenue = get_installation_unit_revenue_split(service, unit)
                        else:
                            unit_sub_revenue = Decimal('0.00')

                        if unit_sub_revenue > 0:
                            sub_unit_items.append({
                                'description': f"Aircon Unit Cost: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                                'price': unit_sub_revenue,
                            })

                # Create Sub stall transaction for parts/unit allocations if needed
                # Only if not already created earlier (check if one exists from the parts_to_sell logic)
                if has_paid_parts or sub_unit_items:
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
                            transaction_type=TransactionType.SERVICE,
                            document_type=DocumentType.SALES_INVOICE,
                            with_2307=False,
                        )

                        for appliance in service.appliances.all():
                            for item_used in appliance.items_used.all():
                                if item_used.is_free:
                                    continue

                                charged_qty = item_used.quantity - item_used.free_quantity
                                if charged_qty > 0:
                                    SalesItem.objects.create(
                                        transaction=sub_receipt,
                                        item=item_used.item,
                                        description='',
                                        quantity=charged_qty,
                                        final_price_per_unit=item_used.discounted_price,
                                    )

                        # Include service-level items in sub receipt
                        for item_used in service.service_items.all():
                            if item_used.is_free:
                                continue

                            charged_qty = item_used.quantity - item_used.free_quantity
                            if charged_qty > 0:
                                SalesItem.objects.create(
                                    transaction=sub_receipt,
                                    item=item_used.item,
                                    description='',
                                    quantity=charged_qty,
                                    final_price_per_unit=item_used.discounted_price,
                                )

                        for unit_item in sub_unit_items:
                            SalesItem.objects.create(
                                transaction=sub_receipt,
                                item=None,
                                description=unit_item['description'],
                                quantity=1,
                                final_price_per_unit=unit_item['price'],
                            )

                        # Link sub receipt to service
                        service.related_sub_transaction = sub_receipt
                        service.save(update_fields=['related_sub_transaction'])
                    elif not service.related_sub_transaction_id:
                        service.related_sub_transaction = existing_sub_transaction
                        service.save(update_fields=['related_sub_transaction'])

                # ----------------------------------------------------------------
                # Backfill SalesPayments for any service payments that were
                # recorded before the main TX existed (e.g. paid with no labor
                # fees set yet, or paid before the service was completed).
                # ----------------------------------------------------------------
                if main_receipt:
                    from sales.models import SalesPayment as SalesPmt
                    existing_svc_payments = service.payments.order_by('payment_date')
                    if existing_svc_payments.exists():
                        # Which sub TX was ultimately used?
                        actual_sub_tx = sub_receipt
                        if actual_sub_tx is None and service.related_sub_transaction_id:
                            actual_sub_tx = service.related_sub_transaction

                        main_total = main_receipt.computed_total or Decimal('0')

                        # Waterfall-allocate any existing service payments to the
                        # new sales transactions: sub stall first, then main.
                        sub_total = (actual_sub_tx.computed_total or Decimal('0')) if actual_sub_tx else Decimal('0')
                        main_filled = Decimal('0')
                        sub_filled = Decimal('0')

                        for svc_payment in existing_svc_payments:
                            m_share, s_share = ServicePaymentManager._waterfall_split(
                                svc_payment.amount,
                                main_total - main_filled,
                                sub_total - sub_filled,
                            )

                            if s_share > 0 and actual_sub_tx:
                                SalesPmt.objects.create(
                                    transaction=actual_sub_tx,
                                    payment_type=svc_payment.payment_type,
                                    amount=s_share,
                                    payment_date=svc_payment.payment_date,
                                )
                                sub_filled += s_share

                            if m_share > 0:
                                SalesPmt.objects.create(
                                    transaction=main_receipt,
                                    payment_type=svc_payment.payment_type,
                                    amount=m_share,
                                    payment_date=svc_payment.payment_date,
                                )
                                main_filled += m_share

            return {
                'service_id': service.id,
                'status': 'completed',
                'revenue': revenue_data,
                'receipt': (main_receipt or sub_receipt).id if (main_receipt or sub_receipt) else (service.related_transaction.id if service.related_transaction else None),
                'main_receipt': main_receipt.id if main_receipt else None,
                'sub_receipt': sub_receipt.id if sub_receipt else None,
                'message': 'Service completed without items/appliances. Add items and create invoice separately.' if not (has_appliances or has_service_items) else 'Service completed successfully.',
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
            transaction_type=TransactionType.SERVICE,
            document_type=DocumentType.OFFICIAL_RECEIPT,
            with_2307=getattr(service, 'with_2307', False),
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
                    unit_price, _ = get_installation_unit_revenue_split(service, unit)
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
                if charged_qty > 0:
                    SalesItem.objects.create(
                        transaction=receipt,
                        item=item_used.item,
                        description='',
                        quantity=charged_qty,
                        final_price_per_unit=item_used.discounted_price,
                    )

        # Add service-level items
        for item_used in service.service_items.all():
            if item_used.is_free:
                continue

            charged_qty = item_used.quantity - item_used.free_quantity
            if charged_qty > 0:
                SalesItem.objects.create(
                    transaction=receipt,
                    item=item_used.item,
                    description='',
                    quantity=charged_qty,
                    final_price_per_unit=item_used.discounted_price,
                )

        # Add extra charges (e.g. special bracket, hauling fee)
        for ec in service.extra_charges.all():
            ec_amount = Decimal(str(ec.amount))
            if ec_amount > 0:
                SalesItem.objects.create(
                    transaction=receipt,
                    item=None,
                    description=ec.name,
                    quantity=1,
                    final_price_per_unit=ec_amount,
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
        Cancel a service: release reserved stock, void transactions,
        clear revenue, cancel pending stock requests, and mark items cancelled.

        Args:
            service: Service instance to cancel
            reason: Cancellation reason
            user: User cancelling the service

        Returns:
            dict with cancellation details including refund_due
        """
        from utils.enums import ServiceStatus, ApplianceStatus
        from inventory.models import StockRequest
        from installations.models import AirconUnit
        from installations.business_logic import AirconInventoryManager

        with transaction.atomic():
            # Re-fetch with row lock to prevent concurrent operations
            from services.models import Service as ServiceModel
            service = ServiceModel.objects.select_for_update().get(pk=service.pk)

            if service.status == ServiceStatus.COMPLETED:
                raise ValidationError(
                    "Cannot cancel a completed service. Use reopen or refund instead."
                )
            if service.status == ServiceStatus.CANCELLED:
                raise ValidationError("Service is already cancelled.")

            released_items = []
            now = timezone.now()

            # ── 1. Release reserved stock & mark items cancelled ──

            # Appliance-level items
            for appliance in service.appliances.all():
                for item_used in appliance.items_used.all():
                    if item_used.stall_stock:
                        StockReservationManager.release_reservation(
                            item=item_used.item,
                            quantity=item_used.quantity,
                            stall_stock=item_used.stall_stock
                        )
                        item_name = item_used.item.name if item_used.item else 'Custom Item'
                        released_items.append({
                            'item': item_name,
                            'quantity': item_used.quantity,
                        })

                    item_used.is_cancelled = True
                    item_used.cancelled_at = now
                    item_used.save(update_fields=['is_cancelled', 'cancelled_at'])

            # Service-level items
            for item_used in service.service_items.all():
                if item_used.stall_stock:
                    StockReservationManager.release_reservation(
                        item=item_used.item,
                        quantity=item_used.quantity,
                        stall_stock=item_used.stall_stock
                    )
                    item_name = item_used.item.name if item_used.item else 'Custom Item'
                    released_items.append({
                        'item': item_name,
                        'quantity': item_used.quantity,
                    })

                item_used.is_cancelled = True
                item_used.cancelled_at = now
                item_used.save(update_fields=['is_cancelled', 'cancelled_at'])

            # ── 1b. Release aircon unit reservations linked to this service ──
            # Find all AirconUnit(s) where installation_service is this service and reserved_by is not None
            reserved_units = AirconUnit.objects.filter(installation_service=service, reserved_by__isnull=False)
            for unit in reserved_units:
                AirconInventoryManager.release_reservation(unit)

            # ── 2. Cancel pending stock requests ──
            pending_cancelled = StockRequest.objects.filter(
                service=service, status='pending'
            ).update(status='cancelled')

            # ── 3. Void related sales transactions ──
            transactions_voided = 0
            for tx_field in ('related_transaction', 'related_sub_transaction'):
                tx = getattr(service, tx_field, None)
                if tx and not tx.voided:
                    tx.voided = True
                    tx.voided_at = now
                    tx.void_reason = f"Service cancelled: {reason}"
                    tx.save(update_fields=['voided', 'voided_at', 'void_reason'])
                    tx.update_payment_status()
                    transactions_voided += 1

            # ── 4. Clear revenue fields ──
            service.main_stall_revenue = Decimal('0.00')
            service.sub_stall_revenue = Decimal('0.00')
            service.total_revenue = Decimal('0.00')

            # ── 5. Update service status ──
            service.status = ServiceStatus.CANCELLED
            service.cancellation_reason = reason
            service.cancellation_date = now
            if reason:
                service.remarks = f"{service.remarks or ''}\n\nCancellation reason: {reason}".strip()
            service.save(update_fields=[
                'status', 'cancellation_reason', 'cancellation_date',
                'remarks', 'main_stall_revenue', 'sub_stall_revenue',
                'total_revenue', 'updated_at',
            ])

            # ── 6. Reset appliance statuses ──
            service.appliances.all().update(status=ApplianceStatus.PENDING)

            # ── 7. Calculate refund due ──
            refund_due = float(service.total_paid)

            return {
                'service_id': service.id,
                'status': 'cancelled',
                'released_items': released_items,
                'transactions_voided': transactions_voided,
                'stock_requests_cancelled': pending_cancelled,
                'refund_due': refund_due,
            }


class ServiceReopenHandler:
    """Handles reopening a completed service for revision."""

    @staticmethod
    def reopen_service(service, reason="", user=None):
        """
        Reopen a completed service so parts/items can be edited.

        Reverses all side effects of complete_service():
        1. Returns consumed stock back to inventory
        2. Voids SalesTransactions created by completion
        3. Resets warranty dates on appliances
        4. Resets aircon unit is_sold flag (installations)
        5. Clears revenue fields
        6. Sets status back to in_progress
        7. Re-reserves stock for existing parts

        ServicePayments (actual money collected) are NOT affected.

        Args:
            service: Service instance to reopen
            reason: Reason for reopening
            user: User reopening the service

        Returns:
            dict with reopen details
        """
        from utils.enums import ServiceStatus, ApplianceStatus, ServiceType

        with transaction.atomic():
            # Re-fetch with row lock to prevent concurrent reopen/cancel
            from services.models import Service as ServiceModel
            service = ServiceModel.objects.select_for_update().get(pk=service.pk)

            if service.status != ServiceStatus.COMPLETED:
                raise ValidationError("Only completed services can be reopened.")

            restored_items = []

            # ── Step 1: Return consumed stock ──
            for appliance in service.appliances.all():
                for item_used in appliance.items_used.all():
                    if not item_used.stall_stock:
                        continue

                    stock = Stock.objects.select_for_update().get(
                        pk=item_used.stall_stock.pk
                    )
                    qty = Decimal(str(item_used.quantity))
                    stock.quantity += qty
                    stock.save(update_fields=['quantity', 'updated_at'])

                    item_name = item_used.item.name if item_used.item else 'Custom Item'
                    restored_items.append({
                        'item': item_name,
                        'quantity': float(qty),
                    })

            # Return consumed stock for service-level items
            for item_used in service.service_items.all():
                if not item_used.stall_stock:
                    continue

                stock = Stock.objects.select_for_update().get(
                    pk=item_used.stall_stock.pk
                )
                qty = Decimal(str(item_used.quantity))
                stock.quantity += qty
                stock.save(update_fields=['quantity', 'updated_at'])

                item_name = item_used.item.name if item_used.item else 'Custom Item'
                restored_items.append({
                    'item': item_name,
                    'quantity': float(qty),
                })

            # ── Step 2: Void SalesTransactions created by completion ──
            void_reason = f"Service reopened: {reason}" if reason else "Service reopened for revision"
            voided_txs = []
            for tx_field in ['related_transaction', 'related_sub_transaction']:
                tx = getattr(service, tx_field, None)
                if tx and not tx.voided:
                    tx.voided = True
                    tx.voided_at = timezone.now()
                    tx.void_reason = void_reason
                    tx.save(update_fields=['voided', 'voided_at', 'void_reason'])
                    tx.update_payment_status()
                    voided_txs.append(tx.id)

            # Unlink transactions from service
            service.related_transaction = None
            service.related_sub_transaction = None

            # ── Step 3: Reset warranty dates on appliances ──
            for appliance in service.appliances.all():
                needs_update = False
                if appliance.warranty_start_date:
                    appliance.warranty_start_date = None
                    appliance.labor_warranty_end_date = None
                    appliance.unit_warranty_end_date = None
                    needs_update = True
                if needs_update:
                    appliance.save(update_fields=[
                        'warranty_start_date',
                        'labor_warranty_end_date',
                        'unit_warranty_end_date',
                    ])

            # ── Step 4: Reset aircon unit is_sold (installations) ──
            if service.service_type == ServiceType.INSTALLATION:
                for unit in service.installation_units.all():
                    update_fields = []
                    if unit.is_sold:
                        unit.is_sold = False
                        update_fields.append('is_sold')
                    if unit.warranty_start_date:
                        unit.warranty_start_date = None
                        update_fields.append('warranty_start_date')
                    if update_fields:
                        update_fields.append('updated_at')
                        unit.save(update_fields=update_fields)

            # ── Step 5: Set status to in_progress ──
            service.status = ServiceStatus.IN_PROGRESS
            if reason:
                service.remarks = f"{service.remarks or ''}\n\nReopened: {reason}".strip()

            service.save(update_fields=[
                'related_transaction',
                'related_sub_transaction',
                'status',
                'remarks',
                'updated_at',
            ], skip_validation=True)

            # ── Step 7: Reset appliance statuses to pending ──
            service.appliances.filter(
                status=ApplianceStatus.COMPLETED
            ).update(status=ApplianceStatus.PENDING)

            # ── Step 8: Re-reserve stock for existing parts ──
            re_reserved = []
            for appliance in service.appliances.all():
                for item_used in appliance.items_used.all():
                    if not item_used.stall_stock:
                        continue
                    try:
                        StockReservationManager.reserve_stock(
                            item=item_used.item,
                            quantity=item_used.quantity,
                            stall_stock=item_used.stall_stock,
                        )
                        item_name = item_used.item.name if item_used.item else 'Custom Item'
                        re_reserved.append({
                            'item': item_name,
                            'quantity': float(item_used.quantity),
                        })
                    except ValidationError:
                        # Stock may have been sold elsewhere — skip reservation
                        pass

            # Re-reserve service-level items
            for item_used in service.service_items.all():
                if not item_used.stall_stock:
                    continue
                try:
                    StockReservationManager.reserve_stock(
                        item=item_used.item,
                        quantity=item_used.quantity,
                        stall_stock=item_used.stall_stock,
                    )
                    item_name = item_used.item.name if item_used.item else 'Custom Item'
                    re_reserved.append({
                        'item': item_name,
                        'quantity': float(item_used.quantity),
                    })
                except ValidationError:
                    pass

            # ── Step 9: Recalculate revenue (preserves total for payment display) ──
            RevenueCalculator.calculate_service_revenue(service, save=True)

            return {
                'service_id': service.id,
                'status': 'in_progress',
                'restored_items': restored_items,
                'voided_transactions': voided_txs,
                're_reserved_items': re_reserved,
                'message': 'Service reopened for revision. Edit parts/items then re-complete.',
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


def reopen_service(service, reason="", user=None):
    """Shortcut to reopen a completed service for revision."""
    return ServiceReopenHandler.reopen_service(service, reason=reason, user=user)


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
    def sync_sub_sales_items(service):
        """
        Sync the sub-stall SalesTransaction items to match the current set of
        charged parts on the service.  Call this whenever ApplianceItemUsed or
        ServiceItemUsed records are added/changed/deleted on a *completed*
        service so the sub TX total stays in step with service.sub_stall_revenue.

        Includes:
        - All parts (appliance and service level)
        - Aircon unit cost prices for installation services
        """
        from sales.models import SalesItem

        if not service.related_sub_transaction_id:
            return

        sub_tx = service.related_sub_transaction
        if sub_tx.voided:
            return

        # Rebuild all line items from scratch
        sub_tx.items.all().delete()

        for appliance in service.appliances.all():
            for item_used in appliance.items_used.all():
                if item_used.is_free:
                    continue
                charged_qty = item_used.quantity - item_used.free_quantity
                if charged_qty > 0:
                    SalesItem.objects.create(
                        transaction=sub_tx,
                        item=item_used.item,
                        description='',
                        quantity=charged_qty,
                        final_price_per_unit=item_used.discounted_price,
                    )

        for item_used in service.service_items.all():
            if item_used.is_free:
                continue
            charged_qty = item_used.quantity - item_used.free_quantity
            if charged_qty > 0:
                SalesItem.objects.create(
                    transaction=sub_tx,
                    item=item_used.item,
                    description='',
                    quantity=charged_qty,
                    final_price_per_unit=item_used.discounted_price,
                )

        # Add aircon unit allocation for installation services (Sub stall revenue)
        if service.service_type == 'installation':
            for unit in service.installation_units.all():
                if unit.model:
                    _, unit_sub_revenue = get_installation_unit_revenue_split(service, unit)
                else:
                    unit_sub_revenue = Decimal('0.00')

                if unit_sub_revenue > 0:
                    SalesItem.objects.create(
                        transaction=sub_tx,
                        item=None,
                        description=f"Aircon Unit Cost: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                        quantity=1,
                        final_price_per_unit=unit_sub_revenue,
                    )

        sub_tx.update_payment_status()

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
            if (
                service.service_type == 'installation'
                and appliance.serial_number in installation_unit_serials
            ):
                continue

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
            # Add unit_price only for non-installation appliances.
            if service.service_type != 'installation' and appliance.unit_price:
                SalesItem.objects.create(
                    transaction=sales_transaction,
                    item=None,
                    description=f"Unit: {appliance.brand or ''} {appliance.model or ''} (Second-hand)",
                    quantity=1,
                    final_price_per_unit=appliance.unit_price,
                )

        # Add aircon unit prices for installation services
        if service.service_type == 'installation':
            for unit in service.installation_units.all():
                if unit.model:
                    unit_final_price, _ = get_installation_unit_revenue_split(service, unit)
                else:
                    unit_final_price = Decimal('0.00')

                if unit_final_price > 0:
                    SalesItem.objects.create(
                        transaction=sales_transaction,
                        item=None,
                        description=f"Aircon Unit: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                        quantity=1,
                        final_price_per_unit=unit_final_price,
                    )

        # Add extra charges (e.g. special bracket, hauling fee) to the main transaction
        for ec in service.extra_charges.all():
            ec_amount = Decimal(str(ec.amount))
            if ec_amount > 0:
                SalesItem.objects.create(
                    transaction=sales_transaction,
                    item=None,
                    description=ec.name,
                    quantity=1,
                    final_price_per_unit=ec_amount,
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
                transaction_type=TransactionType.SERVICE,
                document_type=DocumentType.OFFICIAL_RECEIPT,
                with_2307=getattr(service, 'with_2307', False),
            )
            service.related_transaction = sales_transaction
            service.save(update_fields=["related_transaction"])

            # Create sales items for labor fees (main stall)
            if service.service_type != 'installation':
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

            # Add aircon unit prices for installation services (Main stall revenue)
            if service.service_type == 'installation':
                for unit in service.installation_units.all():
                    if unit.model:
                        unit_price, _ = get_installation_unit_revenue_split(service, unit)
                        if unit_price > 0:
                            SalesItem.objects.create(
                                transaction=sales_transaction,
                                item=None,
                                description=f"Aircon Unit: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                                quantity=1,
                                final_price_per_unit=unit_price,
                            )

            # Add extra charges (e.g. special bracket, hauling fee) to the main transaction
            for ec in service.extra_charges.all():
                ec_amount = Decimal(str(ec.amount))
                if ec_amount > 0:
                    SalesItem.objects.create(
                        transaction=sales_transaction,
                        item=None,
                        description=ec.name,
                        quantity=1,
                        final_price_per_unit=ec_amount,
                    )

            # Collect all parts from all appliances + service-level items
            parts_to_add = []
            for appliance in service.appliances.all():
                for item_used in appliance.items_used.all():
                    if item_used.is_free:
                        continue
                    charged_qty = item_used.quantity - item_used.free_quantity
                    if charged_qty > 0:
                        parts_to_add.append({
                            'item': item_used.item,
                            'description': item_used.item.name if item_used.item else 'Custom Item',
                            'quantity': charged_qty,
                            'price': item_used.discounted_price,
                        })

            # Service-level items
            for item_used in service.service_items.all():
                if item_used.is_free:
                    continue
                charged_qty = item_used.quantity - item_used.free_quantity
                if charged_qty > 0:
                    parts_to_add.append({
                        'item': item_used.item,
                        'description': item_used.item.name if item_used.item else 'Custom Item',
                        'quantity': charged_qty,
                        'price': item_used.discounted_price,
                    })

            # Build installation unit allocation lines for sub stall
            sub_unit_items = []
            if service.service_type == 'installation':
                for unit in service.installation_units.all():
                    if unit.model:
                        _, unit_sub_revenue = get_installation_unit_revenue_split(service, unit)
                    else:
                        unit_sub_revenue = Decimal('0.00')

                    if unit_sub_revenue > 0:
                        sub_unit_items.append({
                            'description': f"Aircon Unit Cost: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                            'price': unit_sub_revenue,
                        })

            # Create ONE sub stall transaction for ALL parts/unit allocations (if any)
            sub_sales_transaction = None
            if parts_to_add or sub_unit_items:
                sub_sales_transaction = SalesTransaction.objects.create(
                    stall=sub_stall,
                    client=service.client,
                    sales_clerk=service_payments.first().received_by if service_payments.first().received_by else None,
                    transaction_type=TransactionType.SERVICE,
                    document_type=DocumentType.SALES_INVOICE,
                    with_2307=False,
                )

                # Add all parts to the single sub stall transaction
                for part in parts_to_add:
                    SalesItem.objects.create(
                        transaction=sub_sales_transaction,
                        item=part['item'],
                        description=part['description'],
                        quantity=part['quantity'],
                        final_price_per_unit=part['price'],
                    )

                for unit_item in sub_unit_items:
                    SalesItem.objects.create(
                        transaction=sub_sales_transaction,
                        item=None,
                        description=unit_item['description'],
                        quantity=1,
                        final_price_per_unit=unit_item['price'],
                    )

                service.related_sub_transaction = sub_sales_transaction
                service.save(update_fields=["related_sub_transaction"])

            # Waterfall-allocate payments: fill sub first, then main
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
                if s_share > 0 and sub_sales_transaction:
                    SalesPayment.objects.create(
                        transaction=sub_sales_transaction,
                        payment_type=service_payment.payment_type,
                        amount=s_share,
                        payment_date=service_payment.payment_date,
                    )
                SalesPayment.objects.create(
                    transaction=sales_transaction,
                    payment_type=service_payment.payment_type,
                    amount=m_share,
                    payment_date=service_payment.payment_date,
                )
                main_filled += m_share
                sub_filled += s_share

        return sales_transaction

    @staticmethod
    def create_payment(service, payment_type, amount, received_by=None, notes="", cheque_collection=None, payment_date=None):
        """
        Create a payment for a service.

        Args:
            service: Service instance
            payment_type: Payment type (cash, gcash, etc.)
            amount: Payment amount (Decimal)
            received_by: User who received the payment (optional)
            notes: Additional notes (optional)
            cheque_collection: ChequeCollection instance (optional, for cheque payments)
            payment_date: Explicit payment date override (optional). If not provided
                          and service has transaction_date, payment is backdated to noon
                          of that date for correct remittance attribution.

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

        # Determine effective payment_date
        if payment_date is None and service.transaction_date:
            from datetime import datetime, time as dt_time
            from django.utils import timezone as dj_timezone
            payment_date = dj_timezone.make_aware(
                datetime.combine(service.transaction_date, dt_time(12, 0))
            )

        # Create payment — lock service row to prevent concurrent overpayment
        with transaction.atomic():
            from services.models import Service as ServiceModel
            service = ServiceModel.objects.select_for_update().get(pk=service.pk)

            # Check for overpayment inside atomic block after locking
            balance_due = service.balance_due
            if amount > balance_due:
                raise ValidationError(
                    f"Payment amount (₱{amount}) exceeds balance due (₱{balance_due}). "
                    f"Total revenue: ₱{service.total_revenue}, Already paid: ₱{service.total_paid}"
                )

            payment_kwargs = dict(
                service=service,
                payment_type=payment_type,
                amount=amount,
                received_by=received_by,
                notes=notes,
                cheque_collection=cheque_collection,
            )
            if payment_date is not None:
                payment_kwargs["payment_date"] = payment_date

            payment = ServicePayment.objects.create(**payment_kwargs)
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
                # Collect labor items first to decide whether main TX is needed
                labor_items = []
                if service.service_type != 'installation':
                    for appliance in service.appliances.all():
                        labor_charge = appliance.discounted_labor_fee or Decimal('0.00')
                        if labor_charge > 0 and not appliance.labor_is_free:
                            appliance_name = appliance.appliance_type.name if appliance.appliance_type else "Appliance"
                            brand_info = f" ({appliance.brand})" if appliance.brand else ""
                            labor_items.append({
                                'description': f"Labor Fee - {appliance_name}{brand_info}",
                                'fee': labor_charge,
                            })

                # Collect aircon unit items for installation services
                unit_items = []
                sub_unit_items = []
                if service.service_type == 'installation':
                    for unit in service.installation_units.all():
                        if unit.model:
                            unit_price, sub_unit_price = get_installation_unit_revenue_split(service, unit)
                            if unit_price > 0:
                                unit_items.append({
                                    'description': f"Aircon Unit: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                                    'price': unit_price,
                                })
                            if sub_unit_price > 0:
                                sub_unit_items.append({
                                    'description': f"Aircon Unit Cost: {unit.model.brand.name} {unit.model.name} (SN: {unit.serial_number})",
                                    'price': sub_unit_price,
                                })

                # Only create main stall TX if there are labor/unit items
                if labor_items or unit_items:
                    target_stall = service.stall if service.stall else main_stall
                    sales_transaction = SalesTransaction.objects.create(
                        stall=target_stall,
                        client=service.client,
                        sales_clerk=received_by,
                        transaction_type=TransactionType.SERVICE,
                        document_type=DocumentType.OFFICIAL_RECEIPT,
                        with_2307=getattr(service, 'with_2307', False),
                    )
                    service.related_transaction = sales_transaction

                    for item in labor_items:
                        SalesItem.objects.create(
                            transaction=sales_transaction,
                            item=None,
                            description=item['description'],
                            quantity=1,
                            final_price_per_unit=item['fee'],
                        )

                    for item in unit_items:
                        SalesItem.objects.create(
                            transaction=sales_transaction,
                            item=None,
                            description=item['description'],
                            quantity=1,
                            final_price_per_unit=item['price'],
                        )

                # Collect all parts from all appliances + service-level items
                parts_to_add = []
                for appliance in service.appliances.all():
                    for item_used in appliance.items_used.all():
                        if item_used.is_free:
                            continue
                        charged_qty = item_used.quantity - item_used.free_quantity
                        if charged_qty > 0:
                            parts_to_add.append({
                                'item': item_used.item,
                                'description': item_used.item.name if item_used.item else 'Custom Item',
                                'quantity': charged_qty,
                                'price': item_used.discounted_price,
                            })

                # Service-level items
                for item_used in service.service_items.all():
                    if item_used.is_free:
                        continue
                    charged_qty = item_used.quantity - item_used.free_quantity
                    if charged_qty > 0:
                        parts_to_add.append({
                            'item': item_used.item,
                            'description': item_used.item.name if item_used.item else 'Custom Item',
                            'quantity': charged_qty,
                            'price': item_used.discounted_price,
                        })

                # Find or create sub stall transaction for parts
                if parts_to_add or sub_unit_items:
                    # Check if service already has a linked sub transaction
                    if service.related_sub_transaction_id:
                        try:
                            existing = service.related_sub_transaction
                            if not existing.voided:
                                sub_sales_tx = existing
                        except SalesTransaction.DoesNotExist:
                            pass

                    # Fallback: time-window lookup for transactions from complete_service
                    if not sub_sales_tx and sales_transaction:
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
                            transaction_type=TransactionType.SERVICE,
                            document_type=DocumentType.SALES_INVOICE,
                            with_2307=False,
                        )

                        # Add all parts to the single sub stall transaction
                        for part in parts_to_add:
                            SalesItem.objects.create(
                                transaction=sub_sales_tx,
                                item=part['item'],
                                description=part['description'],
                                quantity=part['quantity'],
                                final_price_per_unit=part['price'],
                            )

                        for unit_item in sub_unit_items:
                            SalesItem.objects.create(
                                transaction=sub_sales_tx,
                                item=None,
                                description=unit_item['description'],
                                quantity=1,
                                final_price_per_unit=unit_item['price'],
                            )

                # Link transactions to service
                if sub_sales_tx:
                    service.related_sub_transaction = sub_sales_tx

                update_fields = ["related_sub_transaction"]
                if sales_transaction:
                    update_fields.append("related_transaction")
                service.save(update_fields=update_fields)

                # Apply service-level discount to Main stall SalesTransaction only
                # Service-level discounts reduce labor/service fees, not parts
                service_discount = Decimal("0")
                if sales_transaction and (service.service_discount_percentage and service.service_discount_percentage > 0):
                    main_subtotal = sales_transaction.subtotal or Decimal("0")
                    sub_subtotal = (sub_sales_tx.subtotal or Decimal("0")) if sub_sales_tx else Decimal("0")
                    combined = main_subtotal + sub_subtotal
                    service_discount = (combined * service.service_discount_percentage / Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                elif service.service_discount_amount and service.service_discount_amount > 0:
                    service_discount = service.service_discount_amount

                if service_discount > 0:
                    main_subtotal = (sales_transaction.subtotal or Decimal("0")) if sales_transaction else Decimal("0")
                    if main_subtotal > 0 and sales_transaction:
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

                # Waterfall-allocate previous service payments: sub first, then main
                main_total = (sales_transaction.computed_total or Decimal("0")) if sales_transaction else Decimal("0")
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
                    if m_share > 0 and sales_transaction:
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

                # Persist the link if found via fallback
                if sub_sales_tx and not service.related_sub_transaction_id:
                    service.related_sub_transaction = sub_sales_tx
                    service.save(update_fields=["related_sub_transaction"])

            # Waterfall-allocate current payment: fill sub first, then main
            main_total = (sales_transaction.computed_total or Decimal("0")) if sales_transaction else Decimal("0")
            sub_total = (sub_sales_tx.computed_total or Decimal("0")) if sub_sales_tx else Decimal("0")
            main_paid = sum(p.amount for p in sales_transaction.payments.all()) if sales_transaction else Decimal("0")
            sub_paid = sum(p.amount for p in sub_sales_tx.payments.all()) if sub_sales_tx else Decimal("0")

            m_share, s_share = ServicePaymentManager._waterfall_split(
                amount,
                main_total - main_paid,
                sub_total - sub_paid,
            )

            if m_share > 0 and sales_transaction:
                sp_kwargs = dict(
                    transaction=sales_transaction,
                    payment_type=payment_type,
                    amount=m_share,
                )
                if payment_date is not None:
                    sp_kwargs["payment_date"] = payment_date
                SalesPayment.objects.create(**sp_kwargs)
            if s_share > 0 and sub_sales_tx:
                sp_kwargs = dict(
                    transaction=sub_sales_tx,
                    payment_type=payment_type,
                    amount=s_share,
                )
                if payment_date is not None:
                    sp_kwargs["payment_date"] = payment_date
                SalesPayment.objects.create(**sp_kwargs)

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
    def update_payment(payment, payment_type=None, amount=None, notes=None, payment_date=None, cheque_collection=None):
        """
        Edit an existing service payment in-place.

        Atomically:
        1. Removes the old SalesPayment mirror(s) from linked transactions
        2. Updates the ServicePayment fields
        3. Re-creates SalesPayment mirror(s) with the new values

        Args:
            payment: ServicePayment instance to update
            payment_type: New payment type (optional — keeps existing if None)
            amount: New amount (optional — keeps existing if None)
            notes: New notes (optional)
            payment_date: New payment date override (optional)
            cheque_collection: New ChequeCollection link (optional)

        Returns:
            Updated ServicePayment instance
        """
        from sales.models import SalesPayment

        with transaction.atomic():
            service = payment.service

            old_amount = payment.amount
            old_type = payment.payment_type

            new_type = payment_type if payment_type is not None else old_type
            new_amount = Decimal(str(amount)) if amount is not None else old_amount

            # Validate new amount won't cause overpayment
            # balance_due includes the current payment, so the headroom is:
            # (balance_due + old_amount) room for the new_amount
            headroom = service.balance_due + old_amount
            if new_amount > headroom:
                raise ValidationError(
                    f"Edited amount (₱{new_amount}) exceeds allowable balance "
                    f"(₱{headroom:.2f})."
                )

            # ── Remove old SalesPayment mirrors ──
            remaining = old_amount
            for tx in [service.related_sub_transaction, service.related_transaction]:
                if not tx or remaining <= 0:
                    continue
                matching = SalesPayment.objects.filter(
                    transaction=tx,
                    payment_type=old_type,
                    amount__lte=remaining,
                ).order_by('-amount')
                for sp in matching:
                    if remaining <= 0:
                        break
                    remaining -= sp.amount
                    sp.delete()
                tx.update_payment_status()

            # ── Apply changes to ServicePayment ──
            payment.payment_type = new_type
            payment.amount = new_amount
            if notes is not None:
                payment.notes = notes
            if payment_date is not None:
                payment.payment_date = payment_date
            if cheque_collection is not None:
                payment.cheque_collection = cheque_collection
            payment.save()

            # ── Re-create SalesPayment mirrors with new values ──
            sales_tx = service.related_transaction
            sub_tx = service.related_sub_transaction

            if sales_tx or sub_tx:
                main_total = (sales_tx.computed_total or Decimal('0')) if sales_tx else Decimal('0')
                sub_total = (sub_tx.computed_total or Decimal('0')) if sub_tx else Decimal('0')
                main_paid = sum(p.amount for p in sales_tx.payments.all()) if sales_tx else Decimal('0')
                sub_paid = sum(p.amount for p in sub_tx.payments.all()) if sub_tx else Decimal('0')

                m_share, s_share = ServicePaymentManager._waterfall_split(
                    new_amount,
                    main_total - main_paid,
                    sub_total - sub_paid,
                )

                sp_kwargs_base = {'payment_type': new_type}
                if payment_date is not None:
                    sp_kwargs_base['payment_date'] = payment_date

                if m_share > 0 and sales_tx:
                    SalesPayment.objects.create(
                        transaction=sales_tx,
                        amount=m_share,
                        **sp_kwargs_base,
                    )
                    sales_tx.update_payment_status()

                if s_share > 0 and sub_tx:
                    SalesPayment.objects.create(
                        transaction=sub_tx,
                        amount=s_share,
                        **sp_kwargs_base,
                    )
                    sub_tx.update_payment_status()

            service.update_payment_status()

        return payment

    @staticmethod
    def void_payment(payment, reason=""):
        """
        Void/delete a payment and update service payment status.
        Also removes the corresponding SalesPayment records from
        related_transaction and related_sub_transaction.

        Args:
            payment: ServicePayment instance
            reason: Reason for voiding (optional)

        Returns:
            Service instance (after update)
        """
        from sales.models import SalesPayment

        with transaction.atomic():
            service = payment.service
            amount = payment.amount
            payment_type = payment.payment_type

            # Remove matching SalesPayment(s) for this service payment.
            # Waterfall: check sub transaction first, then main — mirrors create_payment order.
            remaining = amount
            for tx in [service.related_sub_transaction, service.related_transaction]:
                if not tx or remaining <= 0:
                    continue
                matching = SalesPayment.objects.filter(
                    transaction=tx,
                    payment_type=payment_type,
                    amount__lte=remaining,
                ).order_by('-amount')
                for sp in matching:
                    if remaining <= 0:
                        break
                    remaining -= sp.amount
                    sp.delete()
                tx.update_payment_status()

            payment.delete()
            service.update_payment_status()
            service.refresh_from_db()

        return service


    @staticmethod
    def cancel_service(service, reason=""):
        """
        DEPRECATED: Use ServiceCancellationHandler.cancel_service() instead.
        This method delegates to the handler for a single, correct implementation.
        """
        return ServiceCancellationHandler.cancel_service(
            service=service, reason=reason
        )

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
