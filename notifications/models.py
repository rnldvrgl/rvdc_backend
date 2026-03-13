from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class NotificationType(models.TextChoices):
    """Types of notifications."""
    # Payment notifications
    PAYMENT_RECEIVED = "payment_received", _("Payment Received")
    PAYMENT_REMINDER = "payment_reminder", _("Payment Reminder")
    PAYMENT_OVERDUE = "payment_overdue", _("Payment Overdue")

    # Service notifications
    SERVICE_CREATED = "service_created", _("New Service Created")
    SERVICE_UPDATED = "service_updated", _("Service Updated")
    SERVICE_COMPLETED = "service_completed", _("Service Completed")
    SERVICE_CANCELLED = "service_cancelled", _("Service Cancelled")
    SERVICE_ASSIGNED = "service_assigned", _("Service Assigned to You")
    ITEMS_PENDING_REVIEW = "items_pending_review", _("Items Pending Review")

    # Inventory notifications
    STOCK_LOW = "stock_low", _("Low Stock Alert")
    STOCK_OUT = "stock_out", _("Out of Stock Alert")
    STOCK_REORDER = "stock_reorder", _("Reorder Point Reached")
    STOCK_RESTOCKED = "stock_restocked", _("Stock Restocked")
    STOCK_REQUEST_CREATED = "stock_request_created", _("Stock Request Created")
    STOCK_REQUEST_APPROVED = "stock_request_approved", _("Stock Request Approved")
    STOCK_REQUEST_DECLINED = "stock_request_declined", _("Stock Request Declined")

    # Warranty notifications
    WARRANTY_CLAIM_CREATED = "warranty_claim_created", _("New Warranty Claim")
    WARRANTY_CLAIM_APPROVED = "warranty_claim_approved", _("Warranty Claim Approved")
    WARRANTY_CLAIM_REJECTED = "warranty_claim_rejected", _("Warranty Claim Rejected")
    WARRANTY_EXPIRING = "warranty_expiring", _("Warranty Expiring Soon")
    FREE_CLEANING_AVAILABLE = "free_cleaning_available", _("Free Cleaning Available")

    # Sales notifications
    SALE_CREATED = "sale_created", _("New Sale Created")
    SALE_VOIDED = "sale_voided", _("Sale Voided")

    # System notifications
    SYSTEM_ALERT = "system_alert", _("System Alert")
    REPORT_READY = "report_ready", _("Report Ready")


class Notification(models.Model):
    """
    In-app notification model for RVDC employees.
    Notifications are auto-deleted weekly via cron job.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="User who will receive this notification",
    )

    type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        help_text="Type of notification",
    )

    title = models.CharField(
        max_length=200,
        help_text="Notification title/heading",
    )

    message = models.TextField(
        help_text="Notification message content",
    )

    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional structured data (IDs, links, etc.)",
    )

    # Status tracking
    is_read = models.BooleanField(
        default=False,
        help_text="Whether notification has been read",
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When notification was marked as read",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["type"]),
        ]

    def __str__(self):
        return f"{self.get_type_display()} for {self.user} - {self.title}"

    def mark_as_read(self):
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])
