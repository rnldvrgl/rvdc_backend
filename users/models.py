from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.models import UserManager


class ActiveUserManager(UserManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


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
        upload_to="profile_images/",
        default="profile_image/default_image.jpg",
    )
    is_deleted = models.BooleanField(default=False)

    objects = ActiveUserManager()
    all_objects = UserManager()

    def __str__(self):
        return self.username

    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.save()
