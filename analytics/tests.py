"""
Comprehensive test suite for analytics and reporting.

Tests:
- Revenue analytics (sales + services)
- Payment analytics (collections, payment methods)
- Outstanding balance tracking and aging reports
- Service analytics (performance, technician productivity)
- Warranty analytics
- Client analytics (top clients)
- Inventory analytics (turnover, stock levels)
- Dashboard analytics (consolidated reports)
"""

from datetime import timedelta
from decimal import Decimal

from clients.models import Client
from django.test import TransactionTestCase
from django.utils import timezone
from inventory.models import Item, ProductCategory, Stall, Stock
from rest_framework.test import APITestCase
from sales.models import (
    PaymentStatus as SalesPaymentStatus,
)
from sales.models import (
    PaymentType,
    SalesItem,
    SalesPayment,
    SalesTransaction,
)
from services.models import (
    ApplianceType,
    Service,
    ServicePayment,
    TechnicianAssignment,
)
from services.models import (
    PaymentStatus as ServicePaymentStatus,
)
from users.models import CustomUser
from utils.enums import ServiceStatus, ServiceType


class AnalyticsTestSetupMixin:
    """Mixin to set up test data for analytics tests."""

    @classmethod
    def setUpTestData(cls):
        """Create test data for analytics."""
        # Create stalls
        cls.main_stall = Stall.objects.create(
            name="Main",
            location="Main Location",
            stall_type="main",
            is_system=True,
            inventory_enabled=True,
        )
        cls.sub_stall = Stall.objects.create(
            name="Sub",
            location="Sub Location",
            stall_type="sub",
            is_system=True,
            inventory_enabled=True,
        )

        # Create users
        cls.admin_user = CustomUser.objects.create_user(
            username="admin",
            password="password123",
            role="admin",
            first_name="Admin",
            last_name="User",
        )
        cls.technician1 = CustomUser.objects.create_user(
            username="tech1",
            password="password123",
            role="technician",
            first_name="Tech",
            last_name="One",
        )
        cls.technician2 = CustomUser.objects.create_user(
            username="tech2",
            password="password123",
            role="technician",
            first_name="Tech",
            last_name="Two",
        )

        # Create clients
        cls.client1 = Client.objects.create(
            full_name="John Smith",
            contact_number="09171234567",
            address="123 Main St",
        )
        cls.client2 = Client.objects.create(
            full_name="Jane Doe",
            contact_number="09187654321",
            address="456 Elm St",
        )
        cls.client3 = Client.objects.create(
            full_name="Bob Johnson",
            contact_number="09191112222",
            address="789 Oak Ave",
        )

        # Create product category and items
        cls.category = ProductCategory.objects.create(
            name="Parts",
            description="Appliance parts",
        )
        cls.item1 = Item.objects.create(
            name="Capacitor",
            category=cls.category,
            price=Decimal("100.00"),
            retail_price=Decimal("150.00"),
        )
        cls.item2 = Item.objects.create(
            name="Motor",
            category=cls.category,
            price=Decimal("500.00"),
            retail_price=Decimal("750.00"),
        )

        # Create stock
        cls.stock1 = Stock.objects.create(
            stall=cls.sub_stall,
            item=cls.item1,
            quantity=100,
            low_stock_threshold=10,
        )
        cls.stock2 = Stock.objects.create(
            stall=cls.sub_stall,
            item=cls.item2,
            quantity=50,
            low_stock_threshold=5,
        )

        # Create appliance type
        cls.appliance_type = ApplianceType.objects.create(name="Air Conditioner")


# ----------------------------------
# Revenue Analytics Tests
# ----------------------------------
class RevenueAnalyticsTest(AnalyticsTestSetupMixin, TransactionTestCase):
    """Test revenue analytics."""

    def test_revenue_summary_with_sales_only(self):
        """Test revenue summary with sales transactions only."""
        from analytics.business_logic import RevenueAnalytics

        # Create sales transaction
        transaction = SalesTransaction.objects.create(
            stall=self.main_stall,
            client=self.client1,
            sales_clerk=self.admin_user,
        )
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item1,
            quantity=5,
            final_price_per_unit=Decimal("150.00"),
        )

        # Get revenue summary
        summary = RevenueAnalytics.get_revenue_summary()

        self.assertEqual(summary["sales"]["count"], 1)
        self.assertEqual(summary["sales"]["revenue"], 750.0)  # 5 * 150
        self.assertEqual(summary["services"]["count"], 0)
        self.assertEqual(summary["total_revenue"], 750.0)

    def test_revenue_summary_with_services_only(self):
        """Test revenue summary with services only."""
        from analytics.business_logic import RevenueAnalytics

        # Create service
        service = Service.objects.create(
            client=self.client1,
            stall=self.main_stall,
            service_type=ServiceType.REPAIR,
            total_revenue=Decimal("1000.00"),
            main_stall_revenue=Decimal("600.00"),
            sub_stall_revenue=Decimal("400.00"),
        )

        # Get revenue summary
        summary = RevenueAnalytics.get_revenue_summary()

        self.assertEqual(summary["services"]["count"], 1)
        self.assertEqual(summary["services"]["revenue"], 1000.0)
        self.assertEqual(summary["services"]["main_stall_revenue"], 600.0)
        self.assertEqual(summary["services"]["sub_stall_revenue"], 400.0)
        self.assertEqual(summary["total_revenue"], 1000.0)

    def test_revenue_summary_combined(self):
        """Test revenue summary with both sales and services."""
        from analytics.business_logic import RevenueAnalytics

        # Create sales
        transaction = SalesTransaction.objects.create(
            stall=self.main_stall,
            client=self.client1,
        )
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item1,
            quantity=10,
            final_price_per_unit=Decimal("150.00"),
        )

        # Create service
        Service.objects.create(
            client=self.client2,
            stall=self.main_stall,
            total_revenue=Decimal("2000.00"),
        )

        # Get revenue summary
        summary = RevenueAnalytics.get_revenue_summary()

        self.assertEqual(summary["sales"]["revenue"], 1500.0)
        self.assertEqual(summary["services"]["revenue"], 2000.0)
        self.assertEqual(summary["total_revenue"], 3500.0)

    def test_revenue_over_time_daily(self):
        """Test revenue over time with daily aggregation."""
        from analytics.business_logic import RevenueAnalytics

        today = timezone.now().date()

        # Create sales for today
        transaction = SalesTransaction.objects.create(
            stall=self.main_stall,
            client=self.client1,
        )
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item1,
            quantity=5,
            final_price_per_unit=Decimal("150.00"),
        )

        # Get revenue over time
        data = RevenueAnalytics.get_revenue_over_time(
            start_date=today,
            end_date=today,
            period="day",
        )

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["sales_revenue"], 750.0)


# ----------------------------------
# Payment Analytics Tests
# ----------------------------------
class PaymentAnalyticsTest(AnalyticsTestSetupMixin, TransactionTestCase):
    """Test payment analytics."""

    def test_collection_summary(self):
        """Test payment collection summary."""
        from analytics.business_logic import PaymentAnalytics

        # Create sales transaction with payment
        transaction = SalesTransaction.objects.create(
            stall=self.main_stall,
            client=self.client1,
        )
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item1,
            quantity=5,
            final_price_per_unit=Decimal("150.00"),
        )
        SalesPayment.objects.create(
            transaction=transaction,
            payment_type=PaymentType.CASH,
            amount=Decimal("750.00"),
        )

        # Create service with payment
        service = Service.objects.create(
            client=self.client2,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )
        ServicePayment.objects.create(
            service=service,
            payment_type=PaymentType.GCASH,
            amount=Decimal("500.00"),
        )

        # Get collection summary
        summary = PaymentAnalytics.get_collection_summary()

        self.assertEqual(summary["sales_payments"]["count"], 1)
        self.assertEqual(summary["sales_payments"]["amount"], 750.0)
        self.assertEqual(summary["service_payments"]["count"], 1)
        self.assertEqual(summary["service_payments"]["amount"], 500.0)
        self.assertEqual(summary["total_collected"], 1250.0)

    def test_payment_method_breakdown(self):
        """Test payment method breakdown."""
        from analytics.business_logic import PaymentAnalytics

        # Create cash payments
        transaction1 = SalesTransaction.objects.create(stall=self.main_stall)
        SalesPayment.objects.create(
            transaction=transaction1,
            payment_type=PaymentType.CASH,
            amount=Decimal("500.00"),
        )

        # Create GCash payment
        service = Service.objects.create(
            client=self.client1,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )
        ServicePayment.objects.create(
            service=service,
            payment_type=PaymentType.GCASH,
            amount=Decimal("1000.00"),
        )

        # Get breakdown
        breakdown = PaymentAnalytics.get_payment_method_breakdown()

        # Find cash and gcash entries
        cash_entry = next((x for x in breakdown if x["payment_type"] == "cash"), None)
        gcash_entry = next((x for x in breakdown if x["payment_type"] == "gcash"), None)

        self.assertIsNotNone(cash_entry)
        self.assertIsNotNone(gcash_entry)
        self.assertEqual(cash_entry["amount"], 500.0)
        self.assertEqual(gcash_entry["amount"], 1000.0)


# ----------------------------------
# Outstanding Analytics Tests
# ----------------------------------
class OutstandingAnalyticsTest(AnalyticsTestSetupMixin, TransactionTestCase):
    """Test outstanding balance analytics."""

    def test_outstanding_summary(self):
        """Test outstanding balance summary."""
        from analytics.business_logic import OutstandingAnalytics

        # Create unpaid sales transaction
        transaction = SalesTransaction.objects.create(
            stall=self.main_stall,
            client=self.client1,
            payment_status=SalesPaymentStatus.UNPAID,
        )
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item1,
            quantity=10,
            final_price_per_unit=Decimal("150.00"),
        )

        # Create partial service
        service = Service.objects.create(
            client=self.client2,
            stall=self.main_stall,
            total_revenue=Decimal("2000.00"),
            payment_status=ServicePaymentStatus.PARTIAL,
        )
        ServicePayment.objects.create(
            service=service,
            payment_type=PaymentType.CASH,
            amount=Decimal("1000.00"),
        )

        # Get outstanding summary
        summary = OutstandingAnalytics.get_outstanding_summary()

        self.assertEqual(summary["sales"]["count"], 1)
        self.assertEqual(summary["sales"]["balance_due"], 1500.0)
        self.assertEqual(summary["services"]["count"], 1)
        self.assertEqual(summary["services"]["balance_due"], 1000.0)
        self.assertEqual(summary["total_outstanding"], 2500.0)

    def test_aging_report(self):
        """Test aging report."""
        from analytics.business_logic import OutstandingAnalytics

        # Create old unpaid transaction (90+ days)
        old_date = timezone.now() - timedelta(days=100)
        transaction = SalesTransaction.objects.create(
            stall=self.main_stall,
            client=self.client1,
            payment_status=SalesPaymentStatus.UNPAID,
            created_at=old_date,
        )
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item1,
            quantity=10,
            final_price_per_unit=Decimal("150.00"),
        )

        # Get aging report
        report = OutstandingAnalytics.get_aging_report()

        # Should be in 90+ bucket
        self.assertGreater(report["total"]["days_90_plus"], 0)


# ----------------------------------
# Service Analytics Tests
# ----------------------------------
class ServiceAnalyticsTest(AnalyticsTestSetupMixin, TransactionTestCase):
    """Test service analytics."""

    def test_service_summary(self):
        """Test service performance summary."""
        from analytics.business_logic import ServiceAnalytics

        # Create completed service
        Service.objects.create(
            client=self.client1,
            stall=self.main_stall,
            service_type=ServiceType.REPAIR,
            status=ServiceStatus.COMPLETED,
            total_revenue=Decimal("1000.00"),
        )

        # Create in-progress service
        Service.objects.create(
            client=self.client2,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
            status=ServiceStatus.IN_PROGRESS,
            total_revenue=Decimal("2000.00"),
        )

        # Create cancelled service
        Service.objects.create(
            client=self.client3,
            stall=self.main_stall,
            service_type=ServiceType.CLEANING,
            status=ServiceStatus.CANCELLED,
            total_revenue=Decimal("500.00"),
        )

        # Get service summary
        summary = ServiceAnalytics.get_service_summary()

        self.assertEqual(summary["total_services"], 3)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["in_progress"], 1)
        self.assertEqual(summary["cancelled"], 1)
        self.assertEqual(summary["completion_rate"], 33.33333333333333)

    def test_technician_productivity(self):
        """Test technician productivity report."""
        from analytics.business_logic import ServiceAnalytics

        # Create services for tech1
        service1 = Service.objects.create(
            client=self.client1,
            stall=self.main_stall,
            status=ServiceStatus.COMPLETED,
            total_revenue=Decimal("1000.00"),
        )
        TechnicianAssignment.objects.create(
            service=service1,
            technician=self.technician1,
        )

        service2 = Service.objects.create(
            client=self.client2,
            stall=self.main_stall,
            status=ServiceStatus.COMPLETED,
            total_revenue=Decimal("1500.00"),
        )
        TechnicianAssignment.objects.create(
            service=service2,
            technician=self.technician1,
        )

        # Create service for tech2
        service3 = Service.objects.create(
            client=self.client3,
            stall=self.main_stall,
            status=ServiceStatus.IN_PROGRESS,
            total_revenue=Decimal("500.00"),
        )
        TechnicianAssignment.objects.create(
            service=service3,
            technician=self.technician2,
        )

        # Get productivity report
        report = ServiceAnalytics.get_technician_productivity()

        # Find tech1's data
        tech1_data = next(
            (x for x in report if x["technician_id"] == self.technician1.id), None
        )
        self.assertIsNotNone(tech1_data)
        self.assertEqual(tech1_data["total_assignments"], 2)
        self.assertEqual(tech1_data["completed"], 2)
        self.assertEqual(tech1_data["total_revenue"], 2500.0)


# ----------------------------------
# Client Analytics Tests
# ----------------------------------
class ClientAnalyticsTest(AnalyticsTestSetupMixin, TransactionTestCase):
    """Test client analytics."""

    def test_top_clients(self):
        """Test top clients by spending."""
        from analytics.business_logic import ClientAnalytics

        # Client 1: Sales + Service
        transaction1 = SalesTransaction.objects.create(
            stall=self.main_stall,
            client=self.client1,
        )
        SalesItem.objects.create(
            transaction=transaction1,
            item=self.item1,
            quantity=10,
            final_price_per_unit=Decimal("150.00"),
        )
        Service.objects.create(
            client=self.client1,
            stall=self.main_stall,
            total_revenue=Decimal("2000.00"),
        )

        # Client 2: Sales only
        transaction2 = SalesTransaction.objects.create(
            stall=self.main_stall,
            client=self.client2,
        )
        SalesItem.objects.create(
            transaction=transaction2,
            item=self.item2,
            quantity=2,
            final_price_per_unit=Decimal("750.00"),
        )

        # Get top clients
        top_clients = ClientAnalytics.get_top_clients(limit=10)

        self.assertEqual(len(top_clients), 2)
        # Client 1 should be first (1500 + 2000 = 3500)
        self.assertEqual(top_clients[0]["client_id"], self.client1.id)
        self.assertEqual(top_clients[0]["total_spending"], 3500.0)


# ----------------------------------
# Inventory Analytics Tests
# ----------------------------------
class InventoryAnalyticsTest(AnalyticsTestSetupMixin, TransactionTestCase):
    """Test inventory analytics."""

    def test_inventory_summary(self):
        """Test inventory health summary."""
        from analytics.business_logic import InventoryAnalytics

        # Get inventory summary
        summary = InventoryAnalytics.get_inventory_summary(stall=self.sub_stall)

        self.assertEqual(summary["total_items"], 2)
        self.assertEqual(summary["out_of_stock"], 0)
        # Both items have stock above threshold
        self.assertEqual(summary["healthy_stock"], 2)

    def test_stock_turnover(self):
        """Test stock turnover analysis."""
        from analytics.business_logic import InventoryAnalytics

        # Create sales with items
        transaction = SalesTransaction.objects.create(stall=self.main_stall)
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item1,
            quantity=20,
            final_price_per_unit=Decimal("150.00"),
        )
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item2,
            quantity=5,
            final_price_per_unit=Decimal("750.00"),
        )

        # Get turnover analysis
        turnover = InventoryAnalytics.get_stock_turnover(limit=20)

        # Item1 should be first (20 qty moved)
        self.assertEqual(len(turnover), 2)
        self.assertEqual(turnover[0]["item_id"], self.item1.id)
        self.assertEqual(turnover[0]["quantity_moved"], 20)


# ----------------------------------
# Dashboard Analytics Tests
# ----------------------------------
class DashboardAnalyticsTest(AnalyticsTestSetupMixin, TransactionTestCase):
    """Test consolidated dashboard analytics."""

    def test_dashboard_summary(self):
        """Test comprehensive dashboard summary."""
        from analytics.business_logic import DashboardAnalytics

        # Create some data
        transaction = SalesTransaction.objects.create(
            stall=self.main_stall,
            client=self.client1,
        )
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item1,
            quantity=5,
            final_price_per_unit=Decimal("150.00"),
        )

        service = Service.objects.create(
            client=self.client2,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )

        # Get dashboard summary
        summary = DashboardAnalytics.get_dashboard_summary()

        # Verify all sections present
        self.assertIn("revenue", summary)
        self.assertIn("collections", summary)
        self.assertIn("outstanding", summary)
        self.assertIn("services", summary)
        self.assertIn("inventory", summary)

        # Verify revenue data
        self.assertEqual(summary["revenue"]["total_revenue"], 1750.0)


# ----------------------------------
# API Tests
# ----------------------------------
class AnalyticsAPITest(AnalyticsTestSetupMixin, APITestCase):
    """Test analytics API endpoints."""

    def setUp(self):
        """Set up API client with authentication."""
        self.client.force_authenticate(user=self.admin_user)

    def test_revenue_summary_endpoint(self):
        """Test revenue summary API endpoint."""
        # Create test data
        transaction = SalesTransaction.objects.create(
            stall=self.main_stall,
            client=self.client1,
        )
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item1,
            quantity=5,
            final_price_per_unit=Decimal("150.00"),
        )

        # Call API
        response = self.client.get("/api/analytics/reports/revenue-summary/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("sales", data)
        self.assertIn("services", data)
        self.assertIn("total_revenue", data)

    def test_payment_collections_endpoint(self):
        """Test payment collections API endpoint."""
        # Create payment
        transaction = SalesTransaction.objects.create(stall=self.main_stall)
        SalesPayment.objects.create(
            transaction=transaction,
            payment_type=PaymentType.CASH,
            amount=Decimal("500.00"),
        )

        # Call API
        response = self.client.get("/api/analytics/reports/payment-collections/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_collected", data)

    def test_outstanding_summary_endpoint(self):
        """Test outstanding summary API endpoint."""
        # Create unpaid transaction
        transaction = SalesTransaction.objects.create(
            stall=self.main_stall,
            payment_status=SalesPaymentStatus.UNPAID,
        )
        SalesItem.objects.create(
            transaction=transaction,
            item=self.item1,
            quantity=10,
            final_price_per_unit=Decimal("150.00"),
        )

        # Call API
        response = self.client.get("/api/analytics/reports/outstanding-summary/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_outstanding", data)

    def test_dashboard_endpoint(self):
        """Test dashboard API endpoint."""
        # Call API
        response = self.client.get("/api/analytics/reports/dashboard/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("revenue", data)
        self.assertIn("collections", data)
        self.assertIn("outstanding", data)
        self.assertIn("services", data)
        self.assertIn("inventory", data)

    def test_requires_authentication(self):
        """Test that endpoints require authentication."""
        # Logout
        self.client.force_authenticate(user=None)

        # Try to access endpoint
        response = self.client.get("/api/analytics/reports/revenue-summary/")

        self.assertEqual(response.status_code, 401)
