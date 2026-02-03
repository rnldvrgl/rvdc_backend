from clients.models import Client
from django.conf import settings
from django.db import models
from services.models import Service


class Schedule(models.Model):
    """
    Enhanced schedule model for managing service appointments and activities.
    Supports multiple schedule types: home service, pull-out, return, on-site.
    """

    SCHEDULE_TYPES = [
        ('home_service', 'Home Service'),
        ('pull_out', 'Pull-Out (Pick-up)'),
        ('return', 'Return (Delivery)'),
        ('on_site', 'On-Site Service'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled'),
    ]

    # Core relationships
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='schedules'
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='schedules',
        null=True,
        blank=True,
        help_text='Linked service record'
    )
    technicians = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='schedules',
        limit_choices_to={'role': 'technician', 'is_deleted': False},
        blank=True
    )

    # Schedule details
    schedule_type = models.CharField(
        max_length=20,
        choices=SCHEDULE_TYPES,
        help_text='Type of scheduled activity'
    )
    scheduled_date = models.DateField(
        help_text='Date of the scheduled activity'
    )
    scheduled_time = models.TimeField(
        help_text='Time of the scheduled activity'
    )
    estimated_duration = models.PositiveIntegerField(
        default=60,
        help_text='Estimated duration in minutes'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # Location and contact details
    address = models.TextField(
        blank=True,
        null=True,
        help_text='Service location address (uses client address if not specified)'
    )
    contact_person = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Contact person at location'
    )
    contact_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text='Contact number for appointment'
    )

    # Notes
    notes = models.TextField(
        blank=True,
        null=True,
        help_text='Additional notes or instructions'
    )
    internal_notes = models.TextField(
        blank=True,
        null=True,
        help_text='Internal notes (not visible to client)'
    )

    # Tracking
    actual_start_time = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Actual start time of service'
    )
    actual_end_time = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Actual end time of service'
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='completed_schedules',
        null=True,
        blank=True
    )

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='created_schedules',
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['scheduled_date', 'scheduled_time']
        indexes = [
            models.Index(fields=['scheduled_date'], name='schedules_s_schedul_idx'),
            models.Index(fields=['status'], name='schedules_s_status_idx'),
            models.Index(fields=['service'], name='schedules_s_service_idx'),
        ]

    def __str__(self):
        return f"{self.client.full_name} - {self.get_schedule_type_display()} on {self.scheduled_date} {self.scheduled_time.strftime('%H:%M')}"

    def get_technician_names(self):
        """Get comma-separated list of technician names"""
        return ", ".join([tech.get_full_name() for tech in self.technicians.all()])

    @property
    def is_completed(self):
        """Check if schedule is completed"""
        return self.status == 'completed'

    @property
    def is_overdue(self):
        """Check if schedule is overdue"""
        from django.utils import timezone
        if self.status in ['completed', 'cancelled']:
            return False
        scheduled_datetime = timezone.make_aware(
            timezone.datetime.combine(self.scheduled_date, self.scheduled_time)
        )
        return scheduled_datetime < timezone.now()


class ScheduleStatusHistory(models.Model):
    """
    Track status changes for schedules.
    """
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.CASCADE,
        related_name='status_history'
    )
    status = models.CharField(
        max_length=20,
        choices=Schedule.STATUS_CHOICES
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text='Reason for status change'
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-changed_at']
        verbose_name_plural = 'Schedule Status Histories'

    def __str__(self):
        return f"{self.schedule} - {self.get_status_display()} at {self.changed_at}"
