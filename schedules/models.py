from clients.models import Client
from django.db import models
from users.models import CustomUser


# Create your models here.
class Schedule(models.Model):
    SERVICE_TYPES = [
        ("cleaning", "Cleaning"),
        ("on_site", "On-site"),
        ("in_shop", "In-shop"),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    technicians = models.ManyToManyField(
        CustomUser,
        related_name='schedules',
        limit_choices_to={'role': 'technician', 'is_deleted': False},
        blank=True
    )
    scheduled_datetime = models.DateTimeField()
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPES)

    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scheduled_datetime']

    def __str__(self):
        return f"{self.client.full_name} - {self.service_type} on {self.scheduled_datetime.strftime('%Y-%m-%d %H:%M')}"

    def get_technician_names(self):
        """Get comma-separated list of technician names"""
        return ", ".join([tech.get_full_name() for tech in self.technicians.all()])
