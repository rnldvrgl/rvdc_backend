"""
Notification Business Logic

This module provides comprehensive notification management for RVDC employees.

Features:
- Notification creation and management
- Automatic notifications for various events
- Bulk notification operations
- Notification preferences
- Priority-based notifications
"""


from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

User = get_user_model()


# ----------------------------------
# Notification Manager
# ----------------------------------
class NotificationManager:
    """
    Manager for creating and managing notifications.
    """

    @staticmethod
    def create_notification(
        user,
        notification_type,
        title,
        message,
        priority="normal",
        data=None,
        action_url=None,
        action_text=None,
        expires_at=None,
    ):
        """
        Create a notification for a user.

        Args:
            user: User instance or ID
            notification_type: Type of notification (from NotificationType)
            title: Notification title
            message: Notification message
            priority: Priority level (low, normal, high, urgent)
            data: Additional structured data (dict)
            action_url: URL to navigate when clicked
            action_text: Text for action button
            expires_at: Optional expiration datetime

        Returns:
            Notification instance
        """
        from notifications.models import Notification

        if isinstance(user, int):
            user = User.objects.get(id=user)

        notification = Notification.objects.create(
            user=user,
            type=notification_type,
            title=title,
            message=message,
            priority=priority,
            data=data or {},
            action_url=action_url,
            action_text=action_text,
            expires_at=expires_at,
        )

        return notification

    @staticmethod
    def create_bulk_notifications(users, notification_type, title, message, **kwargs):
        """
        Create the same notification for multiple users.

        Args:
            users: List of User instances or IDs
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            **kwargs: Additional notification fields

        Returns:
            List of created Notification instances
        """
        from notifications.models import Notification

        notifications = []
        for user in users:
            if isinstance(user, int):
                user = User.objects.get(id=user)

            notification = Notification.objects.create(
                user=user,
                type=notification_type,
                title=title,
                message=message,
                priority=kwargs.get("priority", "normal"),
                data=kwargs.get("data", {}),
                action_url=kwargs.get("action_url"),
                action_text=kwargs.get("action_text"),
                expires_at=kwargs.get("expires_at"),
            )
            notifications.append(notification)

        return notifications

    @staticmethod
    def get_user_notifications(user, unread_only=False, include_archived=False):
        """
        Get notifications for a user.

        Args:
            user: User instance
            unread_only: Only return unread notifications
            include_archived: Include archived notifications

        Returns:
            QuerySet of Notification instances
        """
        from notifications.models import Notification

        qs = Notification.objects.filter(user=user)

        if unread_only:
            qs = qs.filter(is_read=False)

        if not include_archived:
            qs = qs.filter(is_archived=False)

        # Exclude expired notifications
        qs = qs.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        )

        return qs.order_by("-created_at")

    @staticmethod
    def get_unread_count(user):
        """
        Get count of unread notifications for a user.

        Args:
            user: User instance

        Returns:
            int: Count of unread notifications
        """
        from notifications.models import Notification

        return Notification.objects.filter(
            user=user,
            is_read=False,
            is_archived=False
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        ).count()

    @staticmethod
    def mark_all_as_read(user):
        """
        Mark all notifications as read for a user.

        Args:
            user: User instance

        Returns:
            int: Number of notifications marked as read
        """
        from notifications.models import Notification

        count = Notification.objects.filter(
            user=user,
            is_read=False,
            is_archived=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )

        return count

    @staticmethod
    def delete_old_notifications(days=90):
        """
        Delete notifications older than specified days.

        Args:
            days: Number of days to keep notifications

        Returns:
            int: Number of notifications deleted
        """
        from datetime import timedelta

        from notifications.models import Notification

        cutoff_date = timezone.now() - timedelta(days=days)
        count, _ = Notification.objects.filter(
            created_at__lt=cutoff_date,
            is_read=True
        ).delete()

        return count

    @staticmethod
    def delete_expired_notifications():
        """
        Delete expired notifications.

        Returns:
            int: Number of notifications deleted
        """
        from notifications.models import Notification

        count, _ = Notification.objects.filter(
            expires_at__lt=timezone.now()
        ).delete()

        return count


# ----------------------------------
# Payment Notifications
# ----------------------------------
class PaymentNotifications:
    """Notifications related to payments."""

    @staticmethod
    def notify_payment_received(payment, service=None, transaction=None):
        """
        Notify when payment is received.

        Args:
            payment: ServicePayment or SalesPayment instance
            service: Service instance (if service payment)
            transaction: SalesTransaction instance (if sales payment)
        """
        from notifications.models import NotificationType

        # Determine context
        if service:
            title = f"Payment Received - Service #{service.id}"
            message = f"Payment of ₱{payment.amount} received for {service.client.full_name}"
            action_url = f"/services/{service.id}"
            action_text = "View Service"
            data = {
                "service_id": service.id,
                "client_id": service.client.id,
                "amount": float(payment.amount),
            }
        else:
            title = f"Payment Received - Sale #{transaction.id}"
            message = f"Payment of ₱{payment.amount} received"
            if transaction.client:
                message += f" from {transaction.client.full_name}"
            action_url = f"/sales/{transaction.id}"
            action_text = "View Sale"
            data = {
                "transaction_id": transaction.id,
                "amount": float(payment.amount),
            }

        # Notify clerks and managers
        users = User.objects.filter(
            role__in=["clerk", "manager", "admin"]
        )

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.PAYMENT_RECEIVED,
            title=title,
            message=message,
            priority="normal",
            data=data,
            action_url=action_url,
            action_text=action_text,
        )

    @staticmethod
    def notify_payment_overdue(service=None, transaction=None):
        """
        Notify about overdue payments.

        Args:
            service: Service instance (if service)
            transaction: SalesTransaction instance (if sale)
        """
        from notifications.models import NotificationType

        if service:
            title = f"Overdue Payment - Service #{service.id}"
            message = f"{service.client.full_name} has overdue payment of ₱{service.balance_due}"
            action_url = f"/services/{service.id}"
            data = {"service_id": service.id, "balance_due": float(service.balance_due)}
        else:
            title = f"Overdue Payment - Sale #{transaction.id}"
            message = "Overdue payment"
            if transaction.client:
                message += f" from {transaction.client.full_name}"
            action_url = f"/sales/{transaction.id}"
            data = {"transaction_id": transaction.id}

        # Notify managers and admin
        users = User.objects.filter(role__in=["manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.PAYMENT_OVERDUE,
            title=title,
            message=message,
            priority="high",
            data=data,
            action_url=action_url,
            action_text="View Details",
        )


# ----------------------------------
# Service Notifications
# ----------------------------------
class ServiceNotifications:
    """Notifications related to services."""

    @staticmethod
    def notify_service_created(service, created_by=None):
        """
        Notify when new service is created.

        Args:
            service: Service instance
            created_by: User who created the service
        """
        from notifications.models import NotificationType

        title = f"New Service Created - #{service.id}"
        message = f"New {service.get_service_type_display()} service for {service.client.full_name}"

        # Notify managers and admin (excluding creator)
        users = User.objects.filter(role__in=["manager", "admin"])
        if created_by:
            users = users.exclude(id=created_by.id)

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.SERVICE_CREATED,
            title=title,
            message=message,
            priority="normal",
            data={
                "service_id": service.id,
                "client_id": service.client.id,
                "service_type": service.service_type,
            },
            action_url=f"/services/{service.id}",
            action_text="View Service",
        )

    @staticmethod
    def notify_service_assigned(service, technician):
        """
        Notify technician when service is assigned to them.

        Args:
            service: Service instance
            technician: User instance (technician)
        """
        from notifications.models import NotificationType

        title = f"Service Assigned to You - #{service.id}"
        message = f"{service.get_service_type_display()} service for {service.client.full_name}"

        NotificationManager.create_notification(
            user=technician,
            notification_type=NotificationType.SERVICE_ASSIGNED,
            title=title,
            message=message,
            priority="high",
            data={
                "service_id": service.id,
                "client_id": service.client.id,
                "service_type": service.service_type,
            },
            action_url=f"/services/{service.id}",
            action_text="View Service",
        )

    @staticmethod
    def notify_service_completed(service):
        """
        Notify when service is completed.

        Args:
            service: Service instance
        """
        from notifications.models import NotificationType

        title = f"Service Completed - #{service.id}"
        message = f"{service.get_service_type_display()} service for {service.client.full_name} is now completed"

        # Notify managers and admin
        users = User.objects.filter(role__in=["manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.SERVICE_COMPLETED,
            title=title,
            message=message,
            priority="normal",
            data={
                "service_id": service.id,
                "client_id": service.client.id,
                "total_revenue": float(service.total_revenue),
            },
            action_url=f"/services/{service.id}",
            action_text="View Service",
        )


# ----------------------------------
# Inventory Notifications
# ----------------------------------
class InventoryNotifications:
    """Notifications related to inventory."""

    @staticmethod
    def notify_low_stock(stock):
        """
        Notify when stock is low.

        Args:
            stock: Stock instance
        """
        from notifications.models import NotificationType

        title = f"Low Stock Alert - {stock.item.name}"
        message = f"{stock.item.name} at {stock.stall.name} is low ({stock.quantity} remaining)"

        # Notify managers and admin
        users = User.objects.filter(role__in=["manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.STOCK_LOW,
            title=title,
            message=message,
            priority="high",
            data={
                "stock_id": stock.id,
                "item_id": stock.item.id,
                "stall_id": stock.stall.id,
                "quantity": stock.quantity,
                "threshold": stock.low_stock_threshold,
            },
            action_url=f"/inventory/stock/{stock.id}",
            action_text="View Stock",
        )

    @staticmethod
    def notify_out_of_stock(stock):
        """
        Notify when stock is out.

        Args:
            stock: Stock instance
        """
        from notifications.models import NotificationType

        title = f"Out of Stock - {stock.item.name}"
        message = f"{stock.item.name} at {stock.stall.name} is out of stock"

        # Notify managers and admin
        users = User.objects.filter(role__in=["manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.STOCK_OUT,
            title=title,
            message=message,
            priority="urgent",
            data={
                "stock_id": stock.id,
                "item_id": stock.item.id,
                "stall_id": stock.stall.id,
            },
            action_url=f"/inventory/stock/{stock.id}",
            action_text="Reorder Now",
        )


# ----------------------------------
# Warranty Notifications
# ----------------------------------
class WarrantyNotifications:
    """Notifications related to warranties."""

    @staticmethod
    def notify_warranty_claim_created(claim):
        """
        Notify when warranty claim is created.

        Args:
            claim: WarrantyClaim instance
        """
        from notifications.models import NotificationType

        title = f"New Warranty Claim - #{claim.id}"
        message = f"Warranty claim for {claim.aircon_unit.client.full_name}"

        # Notify managers and admin
        users = User.objects.filter(role__in=["manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.WARRANTY_CLAIM_CREATED,
            title=title,
            message=message,
            priority="high",
            data={
                "claim_id": claim.id,
                "aircon_unit_id": claim.aircon_unit.id,
                "client_id": claim.aircon_unit.client.id,
            },
            action_url=f"/warranties/claims/{claim.id}",
            action_text="Review Claim",
        )

    @staticmethod
    def notify_warranty_claim_approved(claim):
        """
        Notify when warranty claim is approved.

        Args:
            claim: WarrantyClaim instance
        """
        from notifications.models import NotificationType

        title = f"Warranty Claim Approved - #{claim.id}"
        message = f"Warranty claim for {claim.aircon_unit.client.full_name} has been approved"

        # Notify clerks and technicians
        users = User.objects.filter(role__in=["clerk", "technician"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.WARRANTY_CLAIM_APPROVED,
            title=title,
            message=message,
            priority="normal",
            data={
                "claim_id": claim.id,
                "aircon_unit_id": claim.aircon_unit.id,
            },
            action_url=f"/warranties/claims/{claim.id}",
            action_text="View Claim",
        )


# ----------------------------------
# Helper Functions
# ----------------------------------
def notify_user(user, notification_type, title, message, **kwargs):
    """
    Shortcut to create a notification for a single user.

    Args:
        user: User instance or ID
        notification_type: Type of notification
        title: Notification title
        message: Notification message
        **kwargs: Additional notification fields
    """
    return NotificationManager.create_notification(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        **kwargs
    )


def notify_role(role, notification_type, title, message, **kwargs):
    """
    Shortcut to create notifications for all users with a specific role.

    Args:
        role: User role (admin, manager, clerk, technician)
        notification_type: Type of notification
        title: Notification title
        message: Notification message
        **kwargs: Additional notification fields
    """
    users = User.objects.filter(role=role)
    return NotificationManager.create_bulk_notifications(
        users=users,
        notification_type=notification_type,
        title=title,
        message=message,
        **kwargs
    )


def notify_admins(notification_type, title, message, **kwargs):
    """Shortcut to notify all admins."""
    return notify_role("admin", notification_type, title, message, **kwargs)


def notify_managers(notification_type, title, message, **kwargs):
    """Shortcut to notify all managers."""
    return notify_role("manager", notification_type, title, message, **kwargs)


def get_user_unread_count(user):
    """Shortcut to get unread notification count."""
    return NotificationManager.get_unread_count(user)
