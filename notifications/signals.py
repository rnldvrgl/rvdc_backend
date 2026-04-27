"""
Notification Signals

This module contains Django signals that automatically trigger notifications
for various events in the RVDC system.

Signals are triggered for:
- Payment events (received, overdue)
- Service events (created, assigned, completed, cancelled)
- Inventory events (low stock, out of stock)
- Warranty events (claim created, approved, rejected)
- Sales events (created, voided)
"""

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from notifications.business_logic import (
    InventoryNotifications,
    PaymentNotifications,
    ServiceNotifications,
    WarrantyNotifications,
)

logger = logging.getLogger(__name__)


# ----------------------------------
# WebSocket push on notification creation
# ----------------------------------
@receiver(post_save, sender="notifications.Notification")
def push_notification_via_websocket(sender, instance, created, **kwargs):
    """Send real-time notification and web push for newly created notifications."""
    if not created:
        return

    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer  # type: ignore[import-not-found]

        channel_layer = get_channel_layer()
        if channel_layer is not None:
            from notifications.models import Notification

            unread_count = Notification.objects.filter(
                user=instance.user, is_read=False
            ).count()

            async_to_sync(channel_layer.group_send)(
                f"notifications_{instance.user.id}",
                {
                    "type": "send_notification",
                    "data": {
                        "event": "new_notification",
                        "notification": {
                            "id": instance.id,
                            "type": instance.type,
                            "title": instance.title,
                            "message": instance.message,
                        },
                        "unread_count": unread_count,
                    },
                },
            )

        # Also send Web Push (for mobile/background tabs)
        try:
            from notifications.push import send_web_push

            send_web_push(
                user_id=instance.user.id,
                title=instance.title,
                body=instance.message,
                url=instance.data.get("url", "/notifications"),
                tag=f"notif-{instance.id}",
            )
        except Exception:
            logger.exception("Failed to send web push for notification %s", instance.id)

    except Exception:
        logger.exception("Failed to push notification via WebSocket")


# ----------------------------------
# NOTIFICATIONS PAUSED
# ----------------------------------
# Notification creation is temporarily disabled
# All signals below are commented out

# @receiver(post_save, sender='services.ServicePayment')
# def notify_service_payment_received(sender, instance, created, **kwargs):
#     """Notify when service payment is received."""
#     if created:
#         PaymentNotifications.notify_payment_received(
#             payment=instance,
#             service=instance.service,
#         )


# @receiver(post_save, sender='sales.SalesPayment')
# def notify_sales_payment_received(sender, instance, created, **kwargs):
#     """Notify when sales payment is received."""
#     if created:
#         PaymentNotifications.notify_payment_received(
#             payment=instance,
#             transaction=instance.transaction,
#         )


# ----------------------------------
# Service Signals
# ----------------------------------
# @receiver(post_save, sender='services.Service')
# def notify_service_events(sender, instance, created, **kwargs):
#     """Notify when service is created or updated."""
#     if created:
#         # New service created
#         ServiceNotifications.notify_service_created(instance)
#     else:
#         # Check if service was completed
#         if instance.status == 'completed' and hasattr(instance, '_status_changed'):
#             if instance._status_changed:
#                 ServiceNotifications.notify_service_completed(instance)


# @receiver(pre_save, sender='services.Service')
# def track_service_status_change(sender, instance, **kwargs):
#     """Track status changes for service notifications."""
#     if instance.pk:
#         try:
#             old_instance = sender.objects.get(pk=instance.pk)
#             instance._status_changed = old_instance.status != instance.status
#             instance._old_status = old_instance.status
#         except sender.DoesNotExist:
#             instance._status_changed = False
#     else:
#         instance._status_changed = False


# @receiver(post_save, sender='services.TechnicianAssignment')
# def notify_technician_assignment(sender, instance, created, **kwargs):
#     """Notify technician when service is assigned to them."""
#     if created:
#         ServiceNotifications.notify_service_assigned(
#             service=instance.service,
#             technician=instance.technician,
#         )


# ----------------------------------
# Inventory Signals
# ----------------------------------
# @receiver(post_save, sender='inventory.Stock')
# def notify_stock_levels(sender, instance, created, **kwargs):
#     """Notify when stock is low or out."""
#     if not instance.track_stock:
#         return

#     # Out of stock
#     if instance.quantity == 0:
#         InventoryNotifications.notify_out_of_stock(instance)
#     # Low stock (but not zero)
#     elif instance.quantity <= instance.low_stock_threshold:
#         InventoryNotifications.notify_low_stock(instance)


# ----------------------------------
# Warranty Signals
# ----------------------------------
# @receiver(post_save, sender='installations.WarrantyClaim')
# def notify_warranty_claim_events(sender, instance, created, **kwargs):
#     """Notify when warranty claim is created or status changes."""
#     if created:
#         WarrantyNotifications.notify_warranty_claim_created(instance)
#     else:
#         # Check if status changed to approved
#         if hasattr(instance, '_status_changed') and instance._status_changed:
#             if instance.status == 'approved':
#                 WarrantyNotifications.notify_warranty_claim_approved(instance)


# @receiver(pre_save, sender='installations.WarrantyClaim')
# def track_warranty_status_change(sender, instance, **kwargs):
#     """Track status changes for warranty notifications."""
#     if instance.pk:
#         try:
#             old_instance = sender.objects.get(pk=instance.pk)
#             instance._status_changed = old_instance.status != instance.status
#             instance._old_status = old_instance.status
#         except sender.DoesNotExist:
#             instance._status_changed = False
#     else:
#         instance._status_changed = False


# ----------------------------------
# Helper function to register signals
# ----------------------------------
def register_notification_signals():
    """
    Register all notification signals.

    This function can be called in apps.py to ensure signals are registered.
    """
    # Signals are automatically registered via @receiver decorator
    # This function is here for explicit registration if needed
    pass
