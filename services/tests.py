"""
Comprehensive test suite for two-stall service management.

Tests:
- Stock reservation, release, and consumption
- Service creation, completion, and cancellation workflows
- Revenue calculation and attribution
- Promo application (free installation, copper tube)
- Error handling and edge cases
"""

from decimal import Decimal

from clients.models import Client
from django.test import TestCase, TransactionTestCase
from inventory.models import Item, ProductCategory, Stall, Stock
from rest_framework.exceptions import ValidationError
from users.models import CustomUser
from utils.enums import ServiceStatus

from services.business_logic import (
    PromoManager,
    RevenueCalculator,
    ServiceCancellationHandler,
    ServiceCompletionHandler,
    StockReservationManager,
    calculate_revenue,
    cancel_service,
    complete_service,
    get_main_stall,
    get_sub_stall,
)
from services.models import (
    ApplianceItemUsed,
    ApplianceType,
    Service,
    ServiceAppliance,
)


class StallSetupMixin:
    """Mixin to set up Main and Sub stalls for testing."""

    @classmethod
    def setUpTestData(cls):
        # Create system stalls
        cls.main_stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True,
            inventory_enabled=False,
        )

        cls.sub_stall = Stall.objects.create(
            name="Sub",
            location="Parts",
            stall_type="sub",
            is_system=True,
            inventory_enabled=True,
        )

        # Create test user
        cls.user = CustomUser.objects.create_user(
            username="testuser", password="testpass123", role="admin"
        )

        # Create test client
        cls.client_obj = Client.objects.create(
            name="Test Client", email="test@example.com", phone="555-1234"
        )

        # Create product category
        cls.category = ProductCategory.objects.create(
            name="AC Parts", description="Air conditioning parts"
        )

        # Create test items
        cls.capacitor = Item.objects.create(
            name="Capacitor",
            sku="CAP-001",
            category=cls.category,
            retail_price=Decimal("100.00"),
        )

        cls.copper_tube = Item.objects.create(
            name="Copper Tube",
            sku="CPR-001",
            category=cls.category,
            unit_of_measure="ft",
            retail_price=Decimal("10.00"),
        )

        # Create stock in Sub stall
        cls.capacitor_stock = Stock.objects.create(
            item=cls.capacitor,
            stall=cls.sub_stall,
            quantity=100,
            reserved_quantity=0,
            low_stock_threshold=10,
        )

        cls.copper_stock = Stock.objects.create(
            item=cls.copper_tube,
            stall=cls.sub_stall,
            quantity=500,
            reserved_quantity=0,
            low_stock_threshold=50,
        )

        # Create appliance type
        cls.appliance_type = ApplianceType.objects.create(name="Air Conditioner")


class StockReservationManagerTest(StallSetupMixin, TransactionTestCase):
    """Test StockReservationManager operations."""

    def test_reserve_stock_success(self):
        """Test successful stock reservation."""
        initial_reserved = self.capacitor_stock.reserved_quantity
        initial_qty = self.capacitor_stock.quantity

        reserved_stock = StockReservationManager.reserve_stock(
            item=self.capacitor, quantity=10, stall_stock=self.capacitor_stock
        )

        self.assertEqual(reserved_stock.reserved_quantity, initial_reserved + 10)
        self.assertEqual(reserved_stock.quantity, initial_qty)  # Unchanged

    def test_reserve_stock_auto_resolve(self):
        """Test stock reservation auto-resolves to Sub stall."""
        reserved_stock = StockReservationManager.reserve_stock(
            item=self.capacitor, quantity=5
        )

        self.assertEqual(reserved_stock.stall, self.sub_stall)
        self.assertEqual(reserved_stock.reserved_quantity, 5)

    def test_reserve_stock_insufficient(self):
        """Test reservation fails with insufficient stock."""
        with self.assertRaises(ValidationError) as context:
            StockReservationManager.reserve_stock(
                item=self.capacitor, quantity=150, stall_stock=self.capacitor_stock
            )

        self.assertIn("Insufficient stock", str(context.exception))

    def test_reserve_with_existing_reservation(self):
        """Test reservation when some stock already reserved."""
        # Reserve 30 first
        StockReservationManager.reserve_stock(
            self.capacitor, 30, self.capacitor_stock
        )

        # Try to reserve 80 more (only 70 available)
        with self.assertRaises(ValidationError):
            StockReservationManager.reserve_stock(
                self.capacitor, 80, self.capacitor_stock
            )

        # Reserve 50 more should succeed
        stock = StockReservationManager.reserve_stock(
            self.capacitor, 50, self.capacitor_stock
        )
        self.assertEqual(stock.reserved_quantity, 80)

    def test_release_reservation(self):
        """Test releasing reserved stock."""
        StockReservationManager.reserve_stock(
            self.capacitor, 20, self.capacitor_stock
        )

        StockReservationManager.release_reservation(
            self.capacitor, 20, self.capacitor_stock
        )

        self.capacitor_stock.refresh_from_db()
        self.assertEqual(self.capacitor_stock.reserved_quantity, 0)

    def test_consume_reservation(self):
        """Test consuming reserved stock."""
        initial_qty = self.capacitor_stock.quantity

        StockReservationManager.reserve_stock(
            self.capacitor, 20, self.capacitor_stock
        )

        StockReservationManager.consume_reservation(
            self.capacitor, 20, self.capacitor_stock
        )

        self.capacitor_stock.refresh_from_db()
        self.assertEqual(self.capacitor_stock.reserved_quantity, 0)
        self.assertEqual(self.capacitor_stock.quantity, initial_qty - 20)

    def test_consume_more_than_reserved_fails(self):
        """Test consuming more than reserved fails."""
        StockReservationManager.reserve_stock(
            self.capacitor, 10, self.capacitor_stock
        )

        with self.assertRaises(ValidationError):
            StockReservationManager.consume_reservation(
                self.capacitor, 20, self.capacitor_stock
            )


class PromoManagerTest(StallSetupMixin, TestCase):
    """Test PromoManager operations."""

    def test_free_installation_promo(self):
        """Test free installation promo application."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall
        )
        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type, labor_fee=800.00
        )

        PromoManager.apply_free_installation(appliance)

        self.assertEqual(appliance.labor_original_amount, Decimal("800.00"))
        self.assertEqual(appliance.labor_fee, Decimal("0.00"))
        self.assertTrue(appliance.labor_is_free)

    def test_free_installation_already_free(self):
        """Test free installation on already free labor."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall
        )
        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=0.00,
            labor_is_free=True,
        )

        PromoManager.apply_free_installation(appliance)

        # Should not change
        self.assertIsNone(appliance.labor_original_amount)

    def test_copper_tube_promo_25ft(self):
        """Test copper tube promo with 25ft."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall
        )
        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type
        )
        aiu = ApplianceItemUsed.objects.create(
            appliance=appliance, item=self.copper_tube, quantity=25
        )

        free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(aiu)

        self.assertTrue(applied)
        self.assertEqual(free_qty, 10)
        self.assertEqual(charged_qty, 15)
        self.assertEqual(aiu.free_quantity, 10)
        self.assertEqual(aiu.promo_name, PromoManager.PROMO_COPPER_TUBE_10FT)

    def test_copper_tube_promo_5ft(self):
        """Test copper tube promo with 5ft (all free)."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall
        )
        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type
        )
        aiu = ApplianceItemUsed.objects.create(
            appliance=appliance, item=self.copper_tube, quantity=5
        )

        free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(aiu)

        self.assertTrue(applied)
        self.assertEqual(free_qty, 5)
        self.assertEqual(charged_qty, 0)

    def test_copper_tube_promo_non_copper_item(self):
        """Test copper tube promo on non-copper item."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall
        )
        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type
        )
        aiu = ApplianceItemUsed.objects.create(
            appliance=appliance, item=self.capacitor, quantity=10
        )

        free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(aiu)

        self.assertFalse(applied)
        self.assertEqual(free_qty, 0)
        self.assertEqual(charged_qty, 10)


class RevenueCalculatorTest(StallSetupMixin, TestCase):
    """Test RevenueCalculator operations."""

    def test_calculate_basic_service_revenue(self):
        """Test revenue calculation for basic service."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall
        )

        # Appliance with labor
        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type, labor_fee=500.00
        )

        # Parts: 2 capacitors @ $100 each
        ApplianceItemUsed.objects.create(
            appliance=appliance,
            item=self.capacitor,
            quantity=2,
            free_quantity=0,
        )

        revenue = RevenueCalculator.calculate_service_revenue(service, save=True)

        self.assertEqual(revenue["main_revenue"], Decimal("500.00"))
        self.assertEqual(revenue["sub_revenue"], Decimal("200.00"))
        self.assertEqual(revenue["total_revenue"], Decimal("700.00"))

        # Verify saved to service
        service.refresh_from_db()
        self.assertEqual(service.main_stall_revenue, Decimal("500.00"))
        self.assertEqual(service.sub_stall_revenue, Decimal("200.00"))
        self.assertEqual(service.total_revenue, Decimal("700.00"))

    def test_calculate_revenue_with_free_installation(self):
        """Test revenue calculation with free installation."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall
        )

        # Free installation appliance
        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=0.00,
            labor_is_free=True,
            labor_original_amount=800.00,
        )

        # Parts
        ApplianceItemUsed.objects.create(
            appliance=appliance, item=self.capacitor, quantity=2
        )

        revenue = RevenueCalculator.calculate_service_revenue(service, save=True)

        # Main revenue should be 0 (labor is free)
        self.assertEqual(revenue["main_revenue"], Decimal("0.00"))
        self.assertEqual(revenue["sub_revenue"], Decimal("200.00"))

    def test_calculate_revenue_with_free_items(self):
        """Test revenue calculation with free items."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall
        )

        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type, labor_fee=500.00
        )

        # Free item
        ApplianceItemUsed.objects.create(
            appliance=appliance, item=self.capacitor, quantity=2, is_free=True
        )

        revenue = RevenueCalculator.calculate_service_revenue(service, save=True)

        self.assertEqual(revenue["main_revenue"], Decimal("500.00"))
        self.assertEqual(revenue["sub_revenue"], Decimal("0.00"))  # Free items

    def test_calculate_revenue_with_copper_promo(self):
        """Test revenue calculation with copper tube promo."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall
        )

        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type, labor_fee=500.00
        )

        # 25ft copper: 10ft free, 15ft charged
        ApplianceItemUsed.objects.create(
            appliance=appliance,
            item=self.copper_tube,
            quantity=25,
            free_quantity=10,
        )

        revenue = RevenueCalculator.calculate_service_revenue(service, save=True)

        self.assertEqual(revenue["main_revenue"], Decimal("500.00"))
        self.assertEqual(revenue["sub_revenue"], Decimal("150.00"))  # 15 × $10


class ServiceWorkflowTest(StallSetupMixin, TransactionTestCase):
    """Test complete service workflows."""

    def test_service_creation_reserves_stock(self):
        """Test that creating a service with items reserves stock."""
        initial_qty = self.capacitor_stock.quantity
        initial_reserved = self.capacitor_stock.reserved_quantity

        # Create service
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall, status=ServiceStatus.IN_PROGRESS
        )
        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type, labor_fee=500
        )

        # Reserve stock
        StockReservationManager.reserve_stock(
            self.capacitor, 10, self.capacitor_stock
        )

        ApplianceItemUsed.objects.create(
            appliance=appliance,
            item=self.capacitor,
            quantity=10,
            stall_stock=self.capacitor_stock,
        )

        self.capacitor_stock.refresh_from_db()
        self.assertEqual(self.capacitor_stock.quantity, initial_qty)
        self.assertEqual(
            self.capacitor_stock.reserved_quantity, initial_reserved + 10
        )

    def test_service_completion_workflow(self):
        """Test complete service completion workflow."""
        # Create and set up service
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            status=ServiceStatus.IN_PROGRESS,
        )
        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type, labor_fee=500
        )

        # Reserve stock
        StockReservationManager.reserve_stock(
            self.capacitor, 10, self.capacitor_stock
        )

        aiu = ApplianceItemUsed.objects.create(
            appliance=appliance,
            item=self.capacitor,
            quantity=10,
            stall_stock=self.capacitor_stock,
        )

        initial_qty = self.capacitor_stock.quantity

        # Complete service
        result = ServiceCompletionHandler.complete_service(service, user=self.user)

        # Check stock consumed
        self.capacitor_stock.refresh_from_db()
        self.assertEqual(self.capacitor_stock.quantity, initial_qty - 10)
        self.assertEqual(self.capacitor_stock.reserved_quantity, 0)

        # Check status
        service.refresh_from_db()
        self.assertEqual(service.status, ServiceStatus.COMPLETED)

        # Check revenue
        self.assertEqual(service.main_stall_revenue, Decimal("500.00"))
        self.assertEqual(service.sub_stall_revenue, Decimal("1000.00"))

    def test_service_cancellation_workflow(self):
        """Test service cancellation releases stock."""
        # Create service with reservation
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            status=ServiceStatus.IN_PROGRESS,
        )
        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type
        )

        StockReservationManager.reserve_stock(
            self.capacitor, 10, self.capacitor_stock
        )

        ApplianceItemUsed.objects.create(
            appliance=appliance,
            item=self.capacitor,
            quantity=10,
            stall_stock=self.capacitor_stock,
        )

        initial_reserved = self.capacitor_stock.reserved_quantity

        # Cancel service
        result = ServiceCancellationHandler.cancel_service(
            service, reason="Customer cancelled", user=self.user
        )

        # Check stock released
        self.capacitor_stock.refresh_from_db()
        self.assertEqual(self.capacitor_stock.reserved_quantity, initial_reserved - 10)

        # Check status
        service.refresh_from_db()
        self.assertEqual(service.status, ServiceStatus.CANCELLED)

    def test_cannot_cancel_completed_service(self):
        """Test that completed services cannot be cancelled."""
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            status=ServiceStatus.COMPLETED,
        )

        with self.assertRaises(ValidationError):
            ServiceCancellationHandler.cancel_service(service, reason="Test")

    def test_cannot_complete_already_completed_service(self):
        """Test that already completed services cannot be completed again."""
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            status=ServiceStatus.COMPLETED,
        )

        with self.assertRaises(ValidationError):
            ServiceCompletionHandler.complete_service(service)


class HelperFunctionTest(StallSetupMixin, TestCase):
    """Test helper functions."""

    def test_get_main_stall(self):
        """Test get_main_stall helper."""
        main = get_main_stall()
        self.assertIsNotNone(main)
        self.assertEqual(main.stall_type, "main")
        self.assertTrue(main.is_system)

    def test_get_sub_stall(self):
        """Test get_sub_stall helper."""
        sub = get_sub_stall()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.stall_type, "sub")
        self.assertTrue(sub.is_system)
        self.assertTrue(sub.inventory_enabled)

    def test_complete_service_shortcut(self):
        """Test complete_service shortcut function."""
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            status=ServiceStatus.IN_PROGRESS,
        )

        result = complete_service(service, user=self.user)

        self.assertEqual(result["status"], "completed")
        service.refresh_from_db()
        self.assertEqual(service.status, ServiceStatus.COMPLETED)

    def test_cancel_service_shortcut(self):
        """Test cancel_service shortcut function."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall, status=ServiceStatus.IN_PROGRESS
        )

        result = cancel_service(service, reason="Test cancel", user=self.user)

        self.assertEqual(result["status"], "cancelled")
        service.refresh_from_db()
        self.assertEqual(service.status, ServiceStatus.CANCELLED)

    def test_calculate_revenue_shortcut(self):
        """Test calculate_revenue shortcut function."""
        service = Service.objects.create(
            client=self.client_obj, stall=self.main_stall
        )
        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type, labor_fee=500
        )

        revenue = calculate_revenue(service)

        self.assertIn("main_revenue", revenue)
        self.assertIn("sub_revenue", revenue)
        self.assertIn("total_revenue", revenue)


# ----------------------------------
# Service Payment Tests
# ----------------------------------
class ServicePaymentManagerTest(StallSetupMixin, TransactionTestCase):
    """Test ServicePaymentManager operations."""

    def test_create_payment_success(self):
        """Test successful payment creation."""
        from services.business_logic import ServicePaymentManager
        from services.models import PaymentStatus, PaymentType

        # Create service with revenue
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )

        # Create payment
        payment = ServicePaymentManager.create_payment(
            service=service,
            payment_type=PaymentType.CASH,
            amount=Decimal("500.00"),
            received_by=self.user,
            notes="Partial payment",
        )

        self.assertIsNotNone(payment)
        self.assertEqual(payment.amount, Decimal("500.00"))
        self.assertEqual(payment.payment_type, PaymentType.CASH)
        self.assertEqual(payment.received_by, self.user)
        self.assertEqual(payment.notes, "Partial payment")

        # Check service payment status updated
        service.refresh_from_db()
        self.assertEqual(service.payment_status, PaymentStatus.PARTIAL)
        self.assertEqual(service.total_paid, Decimal("500.00"))
        self.assertEqual(service.balance_due, Decimal("500.00"))

    def test_create_payment_full_amount(self):
        """Test payment for full amount marks service as paid."""
        from services.business_logic import ServicePaymentManager
        from services.models import PaymentStatus, PaymentType

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )

        payment = ServicePaymentManager.create_payment(
            service=service,
            payment_type=PaymentType.GCASH,
            amount=Decimal("1000.00"),
            received_by=self.user,
        )

        service.refresh_from_db()
        self.assertEqual(service.payment_status, PaymentStatus.PAID)
        self.assertEqual(service.total_paid, Decimal("1000.00"))
        self.assertEqual(service.balance_due, Decimal("0.00"))

    def test_create_payment_multiple_partial(self):
        """Test multiple partial payments."""
        from services.business_logic import ServicePaymentManager
        from services.models import PaymentStatus, PaymentType

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )

        # First payment
        ServicePaymentManager.create_payment(
            service=service,
            payment_type=PaymentType.CASH,
            amount=Decimal("300.00"),
            received_by=self.user,
        )
        service.refresh_from_db()
        self.assertEqual(service.payment_status, PaymentStatus.PARTIAL)
        self.assertEqual(service.total_paid, Decimal("300.00"))

        # Second payment
        ServicePaymentManager.create_payment(
            service=service,
            payment_type=PaymentType.CASH,
            amount=Decimal("200.00"),
            received_by=self.user,
        )
        service.refresh_from_db()
        self.assertEqual(service.payment_status, PaymentStatus.PARTIAL)
        self.assertEqual(service.total_paid, Decimal("500.00"))

        # Final payment
        ServicePaymentManager.create_payment(
            service=service,
            payment_type=PaymentType.GCASH,
            amount=Decimal("500.00"),
            received_by=self.user,
        )
        service.refresh_from_db()
        self.assertEqual(service.payment_status, PaymentStatus.PAID)
        self.assertEqual(service.total_paid, Decimal("1000.00"))
        self.assertEqual(service.balance_due, Decimal("0.00"))

    def test_create_payment_overpayment_blocked(self):
        """Test that overpayment is prevented."""
        from services.business_logic import ServicePaymentManager
        from services.models import PaymentType

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )

        # Try to pay more than balance
        with self.assertRaises(ValidationError) as cm:
            ServicePaymentManager.create_payment(
                service=service,
                payment_type=PaymentType.CASH,
                amount=Decimal("1500.00"),
                received_by=self.user,
            )

        self.assertIn("exceeds balance due", str(cm.exception))

    def test_create_payment_negative_amount_blocked(self):
        """Test that negative payment amount is prevented."""
        from services.business_logic import ServicePaymentManager
        from services.models import PaymentType

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )

        with self.assertRaises(ValidationError) as cm:
            ServicePaymentManager.create_payment(
                service=service,
                payment_type=PaymentType.CASH,
                amount=Decimal("-100.00"),
                received_by=self.user,
            )

        self.assertIn("must be greater than zero", str(cm.exception))

    def test_create_payment_zero_amount_blocked(self):
        """Test that zero payment amount is prevented."""
        from services.business_logic import ServicePaymentManager
        from services.models import PaymentType

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )

        with self.assertRaises(ValidationError) as cm:
            ServicePaymentManager.create_payment(
                service=service,
                payment_type=PaymentType.CASH,
                amount=Decimal("0.00"),
                received_by=self.user,
            )

        self.assertIn("must be greater than zero", str(cm.exception))

    def test_get_outstanding_services(self):
        """Test getting services with outstanding balances."""
        from services.business_logic import ServicePaymentManager
        from services.models import PaymentType

        # Create paid service
        paid_service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )
        ServicePaymentManager.create_payment(
            service=paid_service,
            payment_type=PaymentType.CASH,
            amount=Decimal("1000.00"),
            received_by=self.user,
        )

        # Create unpaid service
        unpaid_service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("500.00"),
        )

        # Create partial service
        partial_service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("800.00"),
        )
        ServicePaymentManager.create_payment(
            service=partial_service,
            payment_type=PaymentType.CASH,
            amount=Decimal("300.00"),
            received_by=self.user,
        )

        # Get outstanding services
        outstanding = ServicePaymentManager.get_outstanding_services()

        self.assertEqual(outstanding.count(), 2)
        self.assertIn(unpaid_service, outstanding)
        self.assertIn(partial_service, outstanding)
        self.assertNotIn(paid_service, outstanding)

    def test_get_outstanding_services_by_stall(self):
        """Test getting outstanding services filtered by stall."""
        from services.business_logic import ServicePaymentManager

        # Create unpaid service for main stall
        main_service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("500.00"),
        )

        # Create another stall and unpaid service
        other_stall = Stall.objects.create(
            name="Other", location="Somewhere", stall_type="other"
        )
        other_service = Service.objects.create(
            client=self.client_obj,
            stall=other_stall,
            total_revenue=Decimal("300.00"),
        )

        # Get outstanding for main stall only
        outstanding = ServicePaymentManager.get_outstanding_services(stall=self.main_stall)

        self.assertEqual(outstanding.count(), 1)
        self.assertIn(main_service, outstanding)
        self.assertNotIn(other_service, outstanding)

    def test_get_payment_summary(self):
        """Test getting payment summary for a service."""
        from services.business_logic import ServicePaymentManager
        from services.models import PaymentType

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )

        # Add two payments
        ServicePaymentManager.create_payment(
            service=service,
            payment_type=PaymentType.CASH,
            amount=Decimal("400.00"),
            received_by=self.user,
            notes="First payment",
        )
        ServicePaymentManager.create_payment(
            service=service,
            payment_type=PaymentType.GCASH,
            amount=Decimal("300.00"),
            received_by=self.user,
            notes="Second payment",
        )

        summary = ServicePaymentManager.get_payment_summary(service)

        self.assertEqual(summary["service_id"], service.id)
        self.assertEqual(summary["total_revenue"], 1000.00)
        self.assertEqual(summary["total_paid"], 700.00)
        self.assertEqual(summary["balance_due"], 300.00)
        self.assertEqual(summary["payment_status"], "partial")
        self.assertEqual(len(summary["payments"]), 2)

    def test_void_payment(self):
        """Test voiding a payment."""
        from services.business_logic import ServicePaymentManager
        from services.models import PaymentStatus, PaymentType

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )

        payment = ServicePaymentManager.create_payment(
            service=service,
            payment_type=PaymentType.CASH,
            amount=Decimal("500.00"),
            received_by=self.user,
        )

        service.refresh_from_db()
        self.assertEqual(service.payment_status, PaymentStatus.PARTIAL)

        # Void the payment
        ServicePaymentManager.void_payment(payment, reason="Mistake")

        service.refresh_from_db()
        self.assertEqual(service.payment_status, PaymentStatus.UNPAID)
        self.assertEqual(service.total_paid, Decimal("0.00"))
        self.assertEqual(service.payments.count(), 0)

    def test_payment_with_completed_service(self):
        """Test payment workflow with completed service."""
        from services.business_logic import ServicePaymentManager
        from services.models import PaymentType

        # Create and complete service
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            status=ServiceStatus.IN_PROGRESS,
        )
        appliance = ServiceAppliance.objects.create(
            service=service, appliance_type=self.appliance_type, labor_fee=500
        )

        # Complete service (this calculates revenue)
        complete_service(service, user=self.user)

        service.refresh_from_db()
        total_revenue = service.total_revenue

        # Now make payment
        payment = ServicePaymentManager.create_payment(
            service=service,
            payment_type=PaymentType.CASH,
            amount=total_revenue,
            received_by=self.user,
        )

        service.refresh_from_db()
        self.assertEqual(service.payment_status, "paid")
        self.assertEqual(service.balance_due, Decimal("0.00"))
