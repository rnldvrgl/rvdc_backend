from clients.models import Client
from django.core.exceptions import ValidationError
from django.db import models
from services.models import Service
from users.models import CustomUser
from utils.enums import ServiceMode


class ScheduleStatus(models.TextChoices):
    """Status choices for schedule entries."""
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    RESCHEDULED = "rescheduled", "Rescheduled"


class ScheduleType(models.TextChoices):
    """Type of scheduled activity."""
    HOME_SERVICE = "home_service", "Home Service"
    PULL_OUT = "pull_out", "Pull-Out (Pick-up)"
    RETURN = "return", "Return (Delivery)"
    ON_SITE = "on_site", "On-Site Service"


class Schedule(models.Model):
    """
    Simple schedule model for service appointments.

    Tracks technician appointments for:
    - Home service visits
    - Pull-out (pick-up) appointments
    - Return (delivery) appointments
    """

    # Link to service
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="schedules",
        help_text="Linked service record"
    )

    # Client information
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="schedules"
    )

    # Technician assignment
    technician = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedules",
        limit_choices_to={"role": "technician"}
    )

    # Schedule details
    schedule_type = models.CharField(
        max_length=20,
        choices=ScheduleType.choices,
        help_text="Type of scheduled activity"
    )

    scheduled_date = models.DateField(
        help_text="Date of the scheduled activity"
    )

    scheduled_time = models.TimeField(
        help_text="Time of the scheduled activity"
    )

    estimated_duration = models.PositiveIntegerField(
        default=60,
        help_text="Estimated duration in minutes"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=ScheduleStatus.choices,
        default=ScheduleStatus.PENDING
    )

    # Location information
    address = models.TextField(
        blank=True,
        null=True,
        help_text="Service location address (uses client address if not specified)"
    )

    contact_person = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Contact person at location"
    )

    contact_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Contact number for appointment"
    )

    # Notes
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes or instructions"
    )

    internal_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Internal notes (not visible to client)"
    )

    # Completion tracking
    actual_start_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Actual start time of service"
    )

    actual_end_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Actual end time of service"
    )

    completed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_schedules"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_schedules"
    )

    class Meta:
        ordering = ["scheduled_date", "scheduled_time"]
        indexes = [
            models.Index(fields=["scheduled_date", "technician"]),
            models.Index(fields=["status"]),
            models.Index(fields=["service"]),
        ]

    def __str__(self):
        client_name = self.client.name if hasattr(self.client, 'name') else str(self.client)
        return f"{client_name} - {self.get_schedule_type_display()} on {self.scheduled_date} {self.scheduled_time}"

    def clean(self):
        """Validate schedule data."""
        # Validate technician role
        if self.technician and self.technician.role != "technician":
            raise ValidationError({
                "technician": "Assigned user must have technician role."
            })

        # Validate service mode matches schedule type
        if self.service:
            if self.service.service_mode == ServiceMode.HOME_SERVICE:
                if self.schedule_type not in [ScheduleType.HOME_SERVICE, ScheduleType.ON_SITE]:
                    raise ValidationError({
                        "schedule_type": "Schedule type must match service mode (home_service)."
                    })
            elif self.service.service_mode == ServiceMode.PULL_OUT_RETURN:
                if self.schedule_type not in [ScheduleType.PULL_OUT, ScheduleType.RETURN]:
                    raise ValidationError({
                        "schedule_type": "Schedule type must be pull_out or return for pull_out_return service mode."
                    })

        # Validate completion times
        if self.actual_start_time and self.actual_end_time:
            if self.actual_end_time <= self.actual_start_time:
                raise ValidationError({
                    "actual_end_time": "End time must be after start time."
                })

    @property
    def is_completed(self):
        """Check if schedule is completed."""
        return self.status == ScheduleStatus.COMPLETED

    @property
    def is_cancelled(self):
        """Check if schedule is cancelled."""
        return self.status == ScheduleStatus.CANCELLED

    @property
    def actual_duration_minutes(self):
        """Calculate actual duration in minutes."""
        if self.actual_start_time and self.actual_end_time:
            delta = self.actual_end_time - self.actual_start_time
            return int(delta.total_seconds() / 60)
        return None

    @property
    def location_address(self):
        """Get location address (uses override or client address)."""
        if self.address:
            return self.address
        if self.service and self.service.override_address:
            return self.service.override_address
        return getattr(self.client, 'address', 'No address specified')

    @property
    def location_contact_person(self):
        """Get contact person (uses override or client name)."""
        if self.contact_person:
            return self.contact_person
        if self.service and self.service.override_contact_person:
            return self.service.override_contact_person
        return getattr(self.client, 'name', 'No contact person')

    @property
    def location_contact_number(self):
        """Get contact number (uses override or client phone)."""
        if self.contact_number:
            return self.contact_number
        if self.service and self.service.override_contact_number:
            return self.service.override_contact_number
        return getattr(self.client, 'phone', 'No contact number')


class ScheduleStatusHistory(models.Model):
    """Track schedule status changes for audit trail."""

    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.CASCADE,
        related_name="status_history"
    )

    status = models.CharField(
        max_length=20,
        choices=ScheduleStatus.choices
    )

    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for status change"
    )

    changed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        verbose_name_plural = "Schedule Status Histories"

    def __str__(self):
        return f"{self.schedule} → {self.get_status_display()} @ {self.changed_at}"
