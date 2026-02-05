"""
Analytics Models

Custom calendar events for the analytics dashboard.
"""
from django.db import models
from django.utils import timezone


class CalendarEvent(models.Model):
    """
    Custom calendar event that can be displayed in the analytics calendar.
    
    Types:
    - holiday: Public holidays or company holidays
    - meeting: Team meetings or important appointments
    - maintenance: Scheduled maintenance or downtime
    - training: Training sessions or workshops
    - deadline: Project deadlines or important dates
    - other: Other custom events
    """
    
    EVENT_TYPES = [
        ('holiday', 'Holiday'),
        ('meeting', 'Meeting'),
        ('maintenance', 'Maintenance'),
        ('training', 'Training'),
        ('deadline', 'Deadline'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    event_date = models.DateField()
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPES,
        default='other'
    )
    created_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='calendar_events'
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'calendar_events'
        ordering = ['-event_date', '-created_at']
        indexes = [
            models.Index(fields=['event_date']),
            models.Index(fields=['event_type']),
            models.Index(fields=['is_deleted']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.event_date}"

