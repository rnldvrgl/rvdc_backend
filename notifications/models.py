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

    # Inventory notifications
    STOCK_LOW = "stock_low", _("Low Stock Alert")
    STOCK_OUT = "stock_out", _("Out of Stock Alert")
    STOCK_REORDER = "stock_reorder", _("Reorder Point Reached")

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


class NotificationPriority(models.TextChoices):
    """Priority levels for notifications."""
    LOW = "low", _("Low")
    NORMAL = "normal", _("Normal")
    HIGH = "high", _("High")
    URGENT = "urgent", _("Urgent")


class Notification(models.Model):
    """
    In-app notification model for RVDC employees.

    Tracks all system notifications with read status, priority,
    and actionable links.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="User who will receive this notification"
    )

    type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        help_text="Type of notification"
    )

    priority = models.CharField(
        max_length=10,
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
        help_text="Priority level of notification"
    )

    title = models.CharField(
        max_length=200,
        help_text="Notification title/heading"
    )

    message = models.TextField(
        help_text="Notification message content"
    )

    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional structured data (IDs, links, etc.)"
    )

    # Action/Link
    action_url = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL/route to navigate when notification is clicked"
    )

    action_text = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Text for action button (e.g., 'View Service', 'View Payment')"
    )

    # Status tracking
    is_read = models.BooleanField(
        default=False,
        help_text="Whether notification has been read"
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When notification was marked as read"
    )

    is_archived = models.BooleanField(
        default=False,
        help_text="Whether notification has been archived"
    )

    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When notification was archived"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Expiration (optional)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When notification should expire (optional)"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["type"]),
            models.Index(fields=["priority"]),
        ]

    def __str__(self):
        return f"{self.get_type_display()} for {self.user} - {self.title}"

    def mark_as_read(self):
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    def mark_as_unread(self):
        """Mark notification as unread."""
        if self.is_read:
            self.is_read = False
            self.read_at = None
            self.save(update_fields=["is_read", "read_at"])

    def archive(self):
        """Archive notification."""
        if not self.is_archived:
            self.is_archived = True
            self.archived_at = timezone.now()
            self.save(update_fields=["is_archived", "archived_at"])

    def unarchive(self):
        """Unarchive notification."""
        if self.is_archived:
            self.is_archived = False
            self.archived_at = None
            self.save(update_fields=["is_archived", "archived_at"])

    @property
    def is_expired(self):
        """Check if notification has expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
