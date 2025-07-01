from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.models import UserManager
from inventory.models import Stall


class ActiveUserManager(UserManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("manager", "Manager"),
        ("technician", "Technician"),
    )

    username = models.CharField(max_length=150, unique=True, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    password = models.CharField(max_length=128, blank=True)
    assigned_stall = models.ForeignKey(
        Stall, null=True, blank=True, on_delete=models.SET_NULL
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    birthday = models.DateField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    contact_number = models.CharField(max_length=15, null=True, blank=True)
    profile_image = models.ImageField(
        upload_to="profile_images/",
        default="images/default_image.jpg",
    )
    is_deleted = models.BooleanField(default=False)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    objects = ActiveUserManager()
    all_objects = UserManager()

    def __str__(self):
        return f"{self.get_full_name() or self.email or self.pk}"

    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.save()
