"""
Comprehensive test suite for notification system.

Tests:
- Notification model and methods
- Notification manager operations
- Notification API endpoints
- Notification filtering and querying
"""

from datetime import timedelta
from decimal import Decimal

from clients.models import Client
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone
from inventory.models import Item, ProductCategory, Stall, Stock
from rest_framework.test import APITestCase
from services.models import (
    ApplianceType,
    Service,
    ServicePayment,
)
from utils.enums import ServiceType

from notifications.business_logic import (
    InventoryNotifications,
    NotificationManager,
    PaymentNotifications,
    ServiceNotifications,
)
from notifications.models import Notification, NotificationType

User = get_user_model()


class NotificationTestSetupMixin:
    """Mixin to set up test data for notification tests."""

    @classmethod
    def setUpTestData(cls):
        """Create test data for notifications."""
        # Create users
        cls.admin_user = User.objects.create_user(
            username="admin",
            password="password123",
            role="admin",
            first_name="Admin",
            last_name="User",
            email="admin@rvdc.com",
        )
        cls.manager_user = User.objects.create_user(
            username="manager",
            password="password123",
            role="manager",
            first_name="Manager",
            last_name="User",
            email="manager@rvdc.com",
        )
        cls.clerk_user = User.objects.create_user(
            username="clerk",
            password="password123",
            role="clerk",
            first_name="Clerk",
            last_name="User",
            email="clerk@rvdc.com",
        )
        cls.technician_user = User.objects.create_user(
            username="tech1",
            password="password123",
            role="technician",
            first_name="Tech",
            last_name="One",
            email="tech1@rvdc.com",
        )

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

        # Create clients
        cls.client = Client.objects.create(
            full_name="John Smith",
            contact_number="09171234567",
            address="123 Main St",
        )

        # Create items
        cls.category = ProductCategory.objects.create(
            name="Parts",
            description="Appliance parts",
        )
        cls.item = Item.objects.create(
            name="Capacitor",
            category=cls.category,
            price=Decimal("100.00"),
            retail_price=Decimal("150.00"),
        )

        # Create stock
        cls.stock = Stock.objects.create(
            stall=cls.sub_stall,
            item=cls.item,
            quantity=50,
            low_stock_threshold=10,
        )

        # Create appliance type
        cls.appliance_type = ApplianceType.objects.create(name="Air Conditioner")


# ----------------------------------
# Notification Model Tests
# ----------------------------------
class NotificationModelTest(NotificationTestSetupMixin, TransactionTestCase):
    """Test Notification model and methods."""

    def test_create_notification(self):
        """Test creating a notification."""
        notification = Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.PAYMENT_RECEIVED,
            title="Payment Received",
            message="Payment of ₱500 received",
        )

        self.assertEqual(notification.user, self.admin_user)
        self.assertEqual(notification.type, NotificationType.PAYMENT_RECEIVED)
        self.assertFalse(notification.is_read)

    def test_mark_as_read(self):
        """Test marking notification as read."""
        notification = Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.SERVICE_CREATED,
            title="New Service",
            message="New service created",
        )

        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

        notification.mark_as_read()

        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_notification_str(self):
        """Test notification string representation."""
        notification = Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.STOCK_LOW,
            title="Low Stock",
            message="Stock is low",
        )
        self.assertIn("Low Stock", str(notification))

    def test_notification_type_display(self):
        """Test type display label."""
        notification = Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.STOCK_RESTOCKED,
            title="Stock Restocked",
            message="Stock was restocked",
        )
        self.assertEqual(notification.get_type_display(), "Stock Restocked")


# ----------------------------------
# Notification Manager Tests
# ----------------------------------
class NotificationManagerTest(NotificationTestSetupMixin, TransactionTestCase):
    """Test NotificationManager operations."""

    def test_create_notification(self):
        """Test creating notification via manager."""
        notification = NotificationManager.create_notification(
            user=self.admin_user,
            notification_type=NotificationType.PAYMENT_RECEIVED,
            title="Payment Received",
            message="Payment of ₱500 received",
            data={"amount": 500},
        )

        self.assertIsNotNone(notification)
        self.assertEqual(notification.user, self.admin_user)
        self.assertEqual(notification.data["amount"], 500)

    def test_create_bulk_notifications(self):
        """Test creating notifications for multiple users."""
        users = [self.admin_user, self.manager_user, self.clerk_user]

        notifications = NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.STOCK_LOW,
            title="Low Stock Alert",
            message="Capacitor stock is low",
        )

        self.assertEqual(len(notifications), 3)
        self.assertEqual(Notification.objects.count(), 3)

        for user in users:
            self.assertTrue(
                Notification.objects.filter(user=user).exists()
            )

    def test_get_user_notifications(self):
        """Test getting notifications for a user."""
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.PAYMENT_RECEIVED,
            title="Payment 1",
            message="Payment received",
        )
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.SERVICE_CREATED,
            title="Service 1",
            message="Service created",
            is_read=True,
        )
        Notification.objects.create(
            user=self.manager_user,
            type=NotificationType.STOCK_LOW,
            title="Stock Alert",
            message="Stock low",
        )

        notifications = NotificationManager.get_user_notifications(self.admin_user)
        self.assertEqual(notifications.count(), 2)

        unread = NotificationManager.get_user_notifications(
            self.admin_user, unread_only=True
        )
        self.assertEqual(unread.count(), 1)

    def test_get_unread_count(self):
        """Test getting unread notification count."""
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.PAYMENT_RECEIVED,
            title="Payment 1",
            message="Payment received",
        )
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.SERVICE_CREATED,
            title="Service 1",
            message="Service created",
        )
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.STOCK_LOW,
            title="Stock Alert",
            message="Stock low",
            is_read=True,
        )

        count = NotificationManager.get_unread_count(self.admin_user)
        self.assertEqual(count, 2)

    def test_mark_all_as_read(self):
        """Test marking all notifications as read."""
        for i in range(3):
            Notification.objects.create(
                user=self.admin_user,
                type=NotificationType.SERVICE_CREATED,
                title=f"Service {i}",
                message="Service created",
            )

        count = NotificationManager.mark_all_as_read(self.admin_user)
        self.assertEqual(count, 3)

        unread_count = NotificationManager.get_unread_count(self.admin_user)
        self.assertEqual(unread_count, 0)

    def test_delete_old_notifications(self):
        """Test deleting old notifications."""
        old_notification = Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.SERVICE_COMPLETED,
            title="Old Service",
            message="Service completed",
            is_read=True,
        )
        old_notification.created_at = timezone.now() - timedelta(days=10)
        old_notification.save()

        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.SERVICE_CREATED,
            title="Recent Service",
            message="Service created",
        )

        count = NotificationManager.delete_old_notifications(days=7)
        self.assertEqual(count, 1)
        self.assertEqual(Notification.objects.count(), 1)


# ----------------------------------
# Payment Notification Tests
# ----------------------------------
class PaymentNotificationTest(NotificationTestSetupMixin, TransactionTestCase):
    """Test payment-related notifications."""

    def test_notify_payment_received_service(self):
        """Test notification when service payment is received."""
        service = Service.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )
        payment = ServicePayment.objects.create(
            service=service,
            payment_type="cash",
            amount=Decimal("500.00"),
        )

        PaymentNotifications.notify_payment_received(payment=payment, service=service)

        notifications = Notification.objects.filter(
            type=NotificationType.PAYMENT_RECEIVED
        )
        self.assertGreater(notifications.count(), 0)

    def test_notify_payment_overdue(self):
        """Test notification for overdue payment."""
        service = Service.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_revenue=Decimal("1000.00"),
        )

        PaymentNotifications.notify_payment_overdue(service=service)

        notifications = Notification.objects.filter(
            type=NotificationType.PAYMENT_OVERDUE
        )
        self.assertGreater(notifications.count(), 0)


# ----------------------------------
# Service Notification Tests
# ----------------------------------
class ServiceNotificationTest(NotificationTestSetupMixin, TransactionTestCase):
    """Test service-related notifications."""

    def test_notify_service_created(self):
        """Test notification when service is created."""
        service = Service.objects.create(
            client=self.client,
            stall=self.main_stall,
            service_type=ServiceType.REPAIR,
        )

        ServiceNotifications.notify_service_created(service)

        notifications = Notification.objects.filter(
            type=NotificationType.SERVICE_CREATED
        )
        self.assertGreater(notifications.count(), 0)

    def test_notify_service_assigned(self):
        """Test notification when service is assigned to technician."""
        service = Service.objects.create(
            client=self.client,
            stall=self.main_stall,
            service_type=ServiceType.REPAIR,
        )

        ServiceNotifications.notify_service_assigned(
            service=service,
            technician=self.technician_user,
        )

        notification = Notification.objects.filter(
            user=self.technician_user,
            type=NotificationType.SERVICE_ASSIGNED,
        ).first()

        self.assertIsNotNone(notification)

    def test_notify_service_completed(self):
        """Test notification when service is completed."""
        service = Service.objects.create(
            client=self.client,
            stall=self.main_stall,
            service_type=ServiceType.REPAIR,
            total_revenue=Decimal("1000.00"),
        )

        ServiceNotifications.notify_service_completed(service)

        notifications = Notification.objects.filter(
            type=NotificationType.SERVICE_COMPLETED
        )
        self.assertGreater(notifications.count(), 0)


# ----------------------------------
# Inventory Notification Tests
# ----------------------------------
class InventoryNotificationTest(NotificationTestSetupMixin, TransactionTestCase):
    """Test inventory-related notifications."""

    def test_notify_low_stock(self):
        """Test notification when stock is low."""
        self.stock.quantity = 5
        self.stock.save()

        InventoryNotifications.notify_low_stock(self.stock)

        notifications = Notification.objects.filter(
            type=NotificationType.STOCK_LOW
        )
        self.assertGreater(notifications.count(), 0)

    def test_notify_out_of_stock(self):
        """Test notification when stock is out."""
        self.stock.quantity = 0
        self.stock.save()

        InventoryNotifications.notify_out_of_stock(self.stock)

        notifications = Notification.objects.filter(
            type=NotificationType.STOCK_OUT
        )
        self.assertGreater(notifications.count(), 0)


# ----------------------------------
# API Tests
# ----------------------------------
class NotificationAPITest(NotificationTestSetupMixin, APITestCase):
    """Test notification API endpoints."""

    def setUp(self):
        """Set up API client with authentication."""
        self.client.force_authenticate(user=self.admin_user)

    def test_list_notifications(self):
        """Test listing notifications."""
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.PAYMENT_RECEIVED,
            title="Payment Received",
            message="Payment received",
        )
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.SERVICE_CREATED,
            title="Service Created",
            message="Service created",
        )

        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)

    def test_unread_count(self):
        """Test getting unread count."""
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.PAYMENT_RECEIVED,
            title="Payment 1",
            message="Payment received",
        )
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.SERVICE_CREATED,
            title="Service 1",
            message="Service created",
        )

        response = self.client.get("/api/notifications/unread-count/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["unread_count"], 2)

    def test_mark_notification_as_read(self):
        """Test marking notification as read."""
        notification = Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.PAYMENT_RECEIVED,
            title="Payment Received",
            message="Payment received",
        )

        response = self.client.post(f"/api/notifications/{notification.id}/mark-read/")
        self.assertEqual(response.status_code, 200)

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_all_as_read(self):
        """Test marking all notifications as read."""
        for i in range(3):
            Notification.objects.create(
                user=self.admin_user,
                type=NotificationType.SERVICE_CREATED,
                title=f"Service {i}",
                message="Service created",
            )

        response = self.client.post("/api/notifications/mark-all-read/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

        unread_count = Notification.objects.filter(
            user=self.admin_user,
            is_read=False
        ).count()
        self.assertEqual(unread_count, 0)

    def test_filter_by_type(self):
        """Test filtering notifications by type."""
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.PAYMENT_RECEIVED,
            title="Payment",
            message="Payment received",
        )
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.SERVICE_CREATED,
            title="Service",
            message="Service created",
        )

        response = self.client.get(
            f"/api/notifications/?type={NotificationType.PAYMENT_RECEIVED}"
        )
        self.assertEqual(response.status_code, 200)

        results = response.data["results"]
        for notif in results:
            self.assertEqual(notif["type"], NotificationType.PAYMENT_RECEIVED)

    def test_requires_authentication(self):
        """Test that endpoints require authentication."""
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, 401)

    def test_user_can_only_see_own_notifications(self):
        """Test users can only see their own notifications."""
        Notification.objects.create(
            user=self.admin_user,
            type=NotificationType.PAYMENT_RECEIVED,
            title="Admin Notification",
            message="For admin",
        )
        Notification.objects.create(
            user=self.manager_user,
            type=NotificationType.SERVICE_CREATED,
            title="Manager Notification",
            message="For manager",
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/api/notifications/")

        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Admin Notification")
