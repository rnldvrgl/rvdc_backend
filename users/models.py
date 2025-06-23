from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.models import User


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("manager", "Manager"),
        ("technician", "Technician"),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    birthday = models.DateField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    contact_number = models.CharField(max_length=15, null=True, blank=True)
    profile_image = models.ImageField(
        upload_to="profile_images/", null=True, blank=True
    )

    def __str__(self):
        return self.username
