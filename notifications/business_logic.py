"""
Notification Business Logic

Provides notification creation and management helpers for RVDC employees.
"""


from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# ----------------------------------
# Notification Manager
# ----------------------------------
class NotificationManager:
    """Manager for creating and managing notifications."""

    @staticmethod
    def create_notification(user, notification_type, title, message, data=None):
        """
        Create a notification for a user.

        Args:
            user: User instance or ID
            notification_type: Type of notification (from NotificationType)
            title: Notification title
            message: Notification message
            data: Additional structured data (dict)

        Returns:
            Notification instance
        """
        from notifications.models import Notification

        if isinstance(user, int):
            user = User.objects.get(id=user)

        return Notification.objects.create(
            user=user,
            type=notification_type,
            title=title,
            message=message,
            data=data or {},
        )

    @staticmethod
    def create_bulk_notifications(users, notification_type, title, message, **kwargs):
        """
        Create the same notification for multiple users.

        Args:
            users: List of User instances or IDs
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            **kwargs: Additional notification fields (data)

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
                data=kwargs.get("data", {}),
            )
            notifications.append(notification)

        return notifications

    @staticmethod
    def get_user_notifications(user, unread_only=False):
        """
        Get notifications for a user.

        Args:
            user: User instance
            unread_only: Only return unread notifications

        Returns:
            QuerySet of Notification instances
        """
        from notifications.models import Notification

        qs = Notification.objects.filter(user=user)

        if unread_only:
            qs = qs.filter(is_read=False)

        return qs.order_by("-created_at")

    @staticmethod
    def get_unread_count(user):
        """Get count of unread notifications for a user."""
        from notifications.models import Notification

        return Notification.objects.filter(user=user, is_read=False).count()

    @staticmethod
    def mark_all_as_read(user):
        """Mark all notifications as read for a user."""
        from notifications.models import Notification

        return Notification.objects.filter(
            user=user,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

    @staticmethod
    def delete_old_notifications(days=7):
        """Delete notifications older than specified days."""
        from datetime import timedelta

        from notifications.models import Notification

        cutoff_date = timezone.now() - timedelta(days=days)
        count, _ = Notification.objects.filter(created_at__lt=cutoff_date).delete()
        return count


# ----------------------------------
# Payment Notifications
# ----------------------------------
class PaymentNotifications:
    """Notifications related to payments."""

    @staticmethod
    def notify_payment_received(payment, service=None, transaction=None):
        """Notify when payment is received."""
        from notifications.models import NotificationType

        if service:
            title = f"Payment Received - Service #{service.id}"
            message = f"Payment of ₱{payment.amount} received for {service.client.full_name}"
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
            data = {
                "transaction_id": transaction.id,
                "amount": float(payment.amount),
            }

        users = User.objects.filter(role__in=["clerk", "manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.PAYMENT_RECEIVED,
            title=title,
            message=message,
            data=data,
        )

    @staticmethod
    def notify_payment_overdue(service=None, transaction=None):
        """Notify about overdue payments."""
        from notifications.models import NotificationType

        if service:
            title = f"Overdue Payment - Service #{service.id}"
            message = f"{service.client.full_name} has overdue payment of ₱{service.balance_due}"
            data = {"service_id": service.id, "balance_due": float(service.balance_due)}
        else:
            title = f"Overdue Payment - Sale #{transaction.id}"
            message = "Overdue payment"
            if transaction.client:
                message += f" from {transaction.client.full_name}"
            data = {"transaction_id": transaction.id}

        users = User.objects.filter(role__in=["manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.PAYMENT_OVERDUE,
            title=title,
            message=message,
            data=data,
        )


# ----------------------------------
# Service Notifications
# ----------------------------------
class ServiceNotifications:
    """Notifications related to services."""

    @staticmethod
    def notify_service_created(service, created_by=None):
        """Notify when new service is created."""
        from notifications.models import NotificationType

        title = f"New Service Created - #{service.id}"
        message = f"New {service.get_service_type_display()} service for {service.client.full_name}"

        users = User.objects.filter(role__in=["manager", "admin"])
        if created_by:
            users = users.exclude(id=created_by.id)

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.SERVICE_CREATED,
            title=title,
            message=message,
            data={
                "service_id": service.id,
                "client_id": service.client.id,
                "service_type": service.service_type,
            },
        )

    @staticmethod
    def notify_service_assigned(service, technician):
        """Notify technician when service is assigned."""
        from notifications.models import NotificationType

        NotificationManager.create_notification(
            user=technician,
            notification_type=NotificationType.SERVICE_ASSIGNED,
            title=f"Service Assigned to You - #{service.id}",
            message=f"{service.get_service_type_display()} service for {service.client.full_name}",
            data={
                "service_id": service.id,
                "client_id": service.client.id,
                "service_type": service.service_type,
            },
        )

    @staticmethod
    def notify_service_completed(service):
        """Notify when service is completed."""
        from notifications.models import NotificationType

        users = User.objects.filter(role__in=["manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.SERVICE_COMPLETED,
            title=f"Service Completed - #{service.id}",
            message=f"{service.get_service_type_display()} service for {service.client.full_name} is now completed",
            data={
                "service_id": service.id,
                "client_id": service.client.id,
                "total_revenue": float(service.total_revenue),
            },
        )


# ----------------------------------
# Inventory Notifications
# ----------------------------------
class InventoryNotifications:
    """Notifications related to inventory."""

    @staticmethod
    def notify_low_stock(stock):
        """Notify when stock is low."""
        from notifications.models import NotificationType

        users = User.objects.filter(role__in=["manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.STOCK_LOW,
            title=f"Low Stock Alert - {stock.item.name}",
            message=f"{stock.item.name} at {stock.stall.name} is low ({stock.quantity} remaining)",
            data={
                "stock_id": stock.id,
                "item_id": stock.item.id,
                "stall_id": stock.stall.id,
                "quantity": stock.quantity,
                "threshold": stock.low_stock_threshold,
            },
        )

    @staticmethod
    def notify_out_of_stock(stock):
        """Notify when stock is out."""
        from notifications.models import NotificationType

        users = User.objects.filter(role__in=["manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.STOCK_OUT,
            title=f"Out of Stock - {stock.item.name}",
            message=f"{stock.item.name} at {stock.stall.name} is out of stock",
            data={
                "stock_id": stock.id,
                "item_id": stock.item.id,
                "stall_id": stock.stall.id,
            },
        )


# ----------------------------------
# Warranty Notifications
# ----------------------------------
class WarrantyNotifications:
    """Notifications related to warranties."""

    @staticmethod
    def notify_warranty_claim_created(claim):
        """Notify when warranty claim is created."""
        from notifications.models import NotificationType

        users = User.objects.filter(role__in=["manager", "admin"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.WARRANTY_CLAIM_CREATED,
            title=f"New Warranty Claim - #{claim.id}",
            message=f"Warranty claim for {claim.aircon_unit.client.full_name}",
            data={
                "claim_id": claim.id,
                "aircon_unit_id": claim.aircon_unit.id,
                "client_id": claim.aircon_unit.client.id,
            },
        )

    @staticmethod
    def notify_warranty_claim_approved(claim):
        """Notify when warranty claim is approved."""
        from notifications.models import NotificationType

        users = User.objects.filter(role__in=["clerk", "technician"])

        NotificationManager.create_bulk_notifications(
            users=users,
            notification_type=NotificationType.WARRANTY_CLAIM_APPROVED,
            title=f"Warranty Claim Approved - #{claim.id}",
            message=f"Warranty claim for {claim.aircon_unit.client.full_name} has been approved",
            data={
                "claim_id": claim.id,
                "aircon_unit_id": claim.aircon_unit.id,
            },
        )


# ----------------------------------
# Attendance Notifications
# ----------------------------------
class AttendanceNotifications:
    """Notifications related to attendance reminders."""

    @staticmethod
    def _create_reminder(user, reminder_kind, title, message, data):
        from notifications.models import Notification, NotificationType

        reminder_key = data.get("reminder_key")
        if reminder_key and Notification.objects.filter(
            user=user,
            type=NotificationType.ATTENDANCE_REMINDER,
            data__reminder_key=reminder_key,
        ).exists():
            return None

        return NotificationManager.create_notification(
            user=user,
            notification_type=NotificationType.ATTENDANCE_REMINDER,
            title=title,
            message=message,
            data={
                **data,
                "kind": reminder_kind,
            },
        )

    @staticmethod
    def notify_clock_in_reminder(
        user,
        reminder_date,
        work_start,
        work_end,
        reminder_window_open,
        reminder_window_close,
        reminder_slot="first",
    ):
        """Notify an employee that they still need to clock in."""
        return AttendanceNotifications._create_reminder(
            user=user,
            reminder_kind="clock_in",
            title="Clock In Reminder",
            message=(
                f"You still need to clock in for {reminder_date:%B %d, %Y}. "
                f"Your shift is open from {work_start} to {work_end}."
            ),
            data={
                "date": reminder_date.isoformat(),
                "work_start": work_start,
                "work_end": work_end,
                "reminder_window_open": reminder_window_open,
                "reminder_window_close": reminder_window_close,
                "reminder_slot": reminder_slot,
                "reminder_key": f"clock_in:{reminder_date.isoformat()}:{reminder_slot}",
                "url": "/attendance/timetable",
            },
        )

    @staticmethod
    def notify_clock_out_reminder(
        user,
        reminder_date,
        work_end,
        reminder_window_open,
        reminder_window_close,
        reminder_slot="first",
    ):
        """Notify an employee that they still need to clock out."""
        return AttendanceNotifications._create_reminder(
            user=user,
            reminder_kind="clock_out",
            title="Clock Out Reminder",
            message=(
                f"You are still clocked in for {reminder_date:%B %d, %Y}. "
                f"Please clock out by {work_end}."
            ),
            data={
                "date": reminder_date.isoformat(),
                "work_end": work_end,
                "reminder_window_open": reminder_window_open,
                "reminder_window_close": reminder_window_close,
                "reminder_slot": reminder_slot,
                "reminder_key": f"clock_out:{reminder_date.isoformat()}:{reminder_slot}",
                "url": "/attendance/timetable",
            },
        )


# ----------------------------------
# Helper Functions
# ----------------------------------
def notify_user(user, notification_type, title, message, **kwargs):
    """Shortcut to create a notification for a single user."""
    return NotificationManager.create_notification(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        data=kwargs.get("data"),
    )


def notify_role(role, notification_type, title, message, **kwargs):
    """Shortcut to create notifications for all users with a specific role."""
    users = User.objects.filter(role=role)
    return NotificationManager.create_bulk_notifications(
        users=users,
        notification_type=notification_type,
        title=title,
        message=message,
        **kwargs,
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
