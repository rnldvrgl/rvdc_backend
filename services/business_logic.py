"""
Business logic for service operations in the two-stall architecture.

This module handles:
- Stock reservation when services are scheduled
- Stock consumption when services are completed
- Revenue attribution (Main vs Sub stall)
- Promo application (free installation, copper tube promos)
- Service cancellation and stock release
"""

from decimal import Decimal

from django.db import transaction
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
            ValidationError: If insufficient stock available
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

            if quantity > available:
                raise ValidationError(
                    f"Insufficient stock for {item.name}. "
                    f"Available: {available}, Requested: {quantity}"
                )

            # Increment reserved quantity
            stall_stock.reserved_quantity += quantity
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

            if stock.reserved_quantity < quantity:
                # Defensive: don't allow negative reservations
                quantity = stock.reserved_quantity

            stock.reserved_quantity -= quantity
            stock.save(update_fields=['reserved_quantity', 'updated_at'])

    @staticmethod
    def consume_reservation(item, quantity, stall_stock):
        """
        Convert reservation to actual consumption (deduct from quantity and reserved_quantity).

        Args:
            item: The Item to consume
            quantity: Quantity to consume
            stall_stock: Stock instance to consume from

        Raises:
            ValidationError: If insufficient reserved or total stock
        """
        with transaction.atomic():
            stock = Stock.objects.select_for_update().get(pk=stall_stock.pk)

            if quantity > stock.reserved_quantity:
                raise ValidationError(
                    f"Cannot consume {quantity} of {item.name}: only {stock.reserved_quantity} reserved."
                )

            if quantity > stock.quantity:
                raise ValidationError(
                    f"Cannot consume {quantity} of {item.name}: only {stock.quantity} in stock."
                )

            # Deduct from both reserved and actual quantity
            stock.reserved_quantity -= quantity
            stock.quantity -= quantity
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

        # Calculate labor fees (Main stall revenue)
        for appliance in service.appliances.all():
            # Use actual labor_fee (which is 0 if free installation applied)
            main_revenue += appliance.labor_fee or Decimal('0.00')

        # Calculate parts revenue (Sub stall revenue)
        for appliance in service.appliances.all():
            for item_used in appliance.items_used.all():
                if item_used.is_free:
                    # Free items don't contribute to revenue
                    continue

                # Calculate charged quantity (total - free_quantity)
                charged_qty = item_used.quantity - item_used.free_quantity

                if charged_qty > 0 and item_used.item:  # Already has check
                    item_revenue = item_used.item.retail_price * charged_qty
                    sub_revenue += item_revenue

        total_revenue = main_revenue + sub_revenue

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
                            unit_price = item_used.item.retail_price
                            total_price = unit_price * charged_qty

                            # Create SalesTransaction for Sub stall (if not exists)
                            if not item_used.expense:
                                # Sub stall sells the part
                                sub_sales = SalesTransaction.objects.create(
                                    stall=sub_stall,
                                    client=service.client,
                                    sales_clerk=user
                                )

                                SalesItem.objects.create(
                                    transaction=sub_sales,
                                    item=item_used.item,
                                    quantity=charged_qty,
                                    final_price_per_unit=unit_price,
                                )

                                # Main stall incurs expense for the part
                                expense = Expense.objects.create(
                                    stall=main_stall,
                                    total_price=total_price,
                                    description=f"Parts for Service #{service.id} - {item_used.item.name}",
                                    created_by=user,
                                    source="service",
                                )

                                ExpenseItem.objects.create(
                                    expense=expense,
                                    item=item_used.item,
                                    quantity=charged_qty,
                                    total_price=total_price,
                                )

                                # Link expense to item_used
                                item_used.expense = expense
                                item_used.save(update_fields=['expense'])

            # Calculate and save revenue attribution
            revenue_data = RevenueCalculator.calculate_service_revenue(service, save=True)

            # Update service status to completed
            service.status = ServiceStatusEnum.COMPLETED
            service.save(update_fields=['status', 'updated_at'])

            # Optionally create a unified receipt for the customer (only if has appliances/items)
            unified_receipt = None
            if create_receipt and service.client and has_appliances:
                unified_receipt = ServiceCompletionHandler._create_unified_receipt(
                    service, user, revenue_data
                )

            return {
                'service_id': service.id,
                'status': 'completed',
                'revenue': revenue_data,
                'receipt': unified_receipt.id if unified_receipt else None,
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

        # Add labor charges
        for appliance in service.appliances.all():
            if appliance.labor_fee > 0:
                SalesItem.objects.create(
                    transaction=receipt,
                    item=None,  # Non-inventory item
                    description=f"Labor: {appliance.appliance_type.name if appliance.appliance_type else 'Service'}",
                    quantity=1,
                    final_price_per_unit=appliance.labor_fee,
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
        Sync sales transaction items with current service appliances' labor fees.
        Updates line items when labor fees change.
        
        Note: Parts are NOT synced here - they have separate sub stall transactions.
        
        Args:
            service: Service instance with related_transaction
        """
        from sales.models import SalesItem
        
        if not service.related_transaction:
            return
            
        sales_transaction = service.related_transaction
        
        # Clear existing items and recreate (LABOR FEES ONLY)
        sales_transaction.items.all().delete()
        
        # Add labor fees for each appliance
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
            
            # Create sales items for labor fees ONLY (main stall)
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
            
            # Recreate all sales payments from service payments (MAIN STALL ONLY)
            for service_payment in service_payments:
                SalesPayment.objects.create(
                    transaction=sales_transaction,
                    payment_type=service_payment.payment_type,
                    amount=service_payment.amount,
                    payment_date=service_payment.payment_date,
                )
        
        return sales_transaction

    @staticmethod
    def create_payment(service, payment_type, amount, received_by=None, notes=""):
        """
        Create a payment for a service.

        Args:
            service: Service instance
            payment_type: Payment type (cash, gcash, etc.)
            amount: Payment amount (Decimal)
            received_by: User who received the payment (optional)
            notes: Additional notes (optional)

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

        # Check for overpayment
        total_revenue = service.total_revenue
        total_paid = service.total_paid
        balance_due = total_revenue - total_paid

        if amount > balance_due:
            raise ValidationError(
                f"Payment amount (₱{amount}) exceeds balance due (₱{balance_due}). "
                f"Total revenue: ₱{total_revenue}, Already paid: ₱{total_paid}"
            )

        # Create payment
        with transaction.atomic():
            payment = ServicePayment.objects.create(
                service=service,
                payment_type=payment_type,
                amount=amount,
                received_by=received_by,
                notes=notes,
            )
            # Payment status is automatically updated by the model's save() method

            # Create or update sales transactions
            # Check if related_transaction exists and is valid (not deleted)
            sales_transaction = None
            if service.related_transaction:
                try:
                    # Try to access the transaction to see if it still exists
                    sales_transaction = service.related_transaction
                    sales_transaction.id  # This will raise DoesNotExist if deleted
                except SalesTransaction.DoesNotExist:
                    # Transaction was deleted, clear the reference
                    service.related_transaction = None
                    sales_transaction = None
            
            # Get system stalls
            main_stall = get_main_stall()
            sub_stall = get_sub_stall()
            
            if not sales_transaction:
                # Create main stall sales transaction for labor fees
                sales_transaction = SalesTransaction.objects.create(
                    stall=service.stall or main_stall,
                    client=service.client,
                    sales_clerk=received_by,
                )
                service.related_transaction = sales_transaction
                service.save(update_fields=["related_transaction"])
                
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
                        sales_clerk=received_by,
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
                
                # Recreate existing service payments with proper allocation
                # Get all previous payments (excluding the current one we just created)
                previous_payments = service.payments.exclude(id=payment.id).order_by('payment_date')
                
                for service_payment in previous_payments:
                    # Allocate each previous payment: prioritize sub stall first
                    remaining = service_payment.amount
                    
                    # 1. Allocate to sub stall first (if it exists and has balance)
                    if sub_sales_transaction:
                        sub_total = sub_sales_transaction.computed_total
                        sub_paid = sub_sales_transaction.total_paid
                        sub_balance = sub_total - sub_paid
                        
                        if sub_balance > 0:
                            sub_payment_amt = min(remaining, sub_balance)
                            SalesPayment.objects.create(
                                transaction=sub_sales_transaction,
                                payment_type=service_payment.payment_type,
                                amount=sub_payment_amt,
                                payment_date=service_payment.payment_date,
                            )
                            remaining -= sub_payment_amt
                    
                    # 2. Allocate remaining to main stall
                    if remaining > 0:
                        SalesPayment.objects.create(
                            transaction=sales_transaction,
                            payment_type=service_payment.payment_type,
                            amount=remaining,
                            payment_date=service_payment.payment_date,
                        )
            else:
                # Find sub stall transaction (if it exists)
                # It will have the same client and be from sub stall, created around the same time as main transaction
                sub_sales_transaction = SalesTransaction.objects.filter(
                    stall=sub_stall,
                    client=service.client,
                    created_at__gte=sales_transaction.created_at,
                ).order_by('created_at').first()
            
            # Allocate payment: prioritize sub stall (parts) first, then main stall (labor)
            remaining_amount = amount
            
            # 1. Allocate to sub stall first (if it exists and has balance)
            if sub_sales_transaction:
                sub_total = sub_sales_transaction.computed_total
                sub_paid = sub_sales_transaction.total_paid
                sub_balance = sub_total - sub_paid
                
                if sub_balance > 0:
                    # Allocate to sub stall
                    sub_payment_amount = min(remaining_amount, sub_balance)
                    SalesPayment.objects.create(
                        transaction=sub_sales_transaction,
                        payment_type=payment_type,
                        amount=sub_payment_amount,
                    )
                    remaining_amount -= sub_payment_amount
            
            # 2. Allocate remaining amount to main stall
            if remaining_amount > 0:
                SalesPayment.objects.create(
                    transaction=sales_transaction,
                    payment_type=payment_type,
                    amount=remaining_amount,
                )

        return payment

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


def create_service_payment(service, payment_type, amount, received_by=None, notes=""):
    """Shortcut to create a service payment."""
    return ServicePaymentManager.create_payment(
        service=service,
        payment_type=payment_type,
        amount=amount,
        received_by=received_by,
        notes=notes,
    )
