from django.db import models
from clients.models import Client
from users.models import CustomUser


# Create your models here.
class Schedule(models.Model):
    SERVICE_TYPES = [
        ("cleaning", "Cleaning"),
        ("on_site", "On-site"),
        ("in_shop", "In-shop"),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    technician = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    scheduled_datetime = models.DateTimeField()
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPES)

    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.client.full_name} - {self.service_type} on {self.scheduled_datetime.strftime('%Y-%m-%d %H:%M')}"
