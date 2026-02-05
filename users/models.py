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
        ("clerk", "Clerk"),
        ("technician", "Technician"),
    )

    username = models.CharField(max_length=150, unique=True, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    password = models.CharField(max_length=128, blank=True, null=True)
    assigned_stall = models.ForeignKey(
        Stall, null=True, blank=True, on_delete=models.SET_NULL
    )
    province = models.CharField(max_length=50, blank=True, null=True)
    city = models.CharField(max_length=50, blank=True, null=True)
    barangay = models.CharField(max_length=50, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    birthday = models.DateField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    contact_number = models.CharField(max_length=15, null=True, blank=True)
    profile_image = models.ImageField(
        upload_to="profile_images/",
        null=True,
        blank=True,
    )
    sss_number = models.CharField(max_length=50, blank=True, null=True)
    philhealth_number = models.CharField(max_length=50, blank=True, null=True)
    tin_number = models.CharField(max_length=50, blank=True, null=True)
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    include_in_payroll = models.BooleanField(
        default=True,
        help_text="Include this employee in payroll generation"
    )
    has_government_benefits = models.BooleanField(
        default=True,
        help_text="Apply government benefits (SSS, PhilHealth, Pag-IBIG, Tax) to this employee"
    )
    is_deleted = models.BooleanField(default=False)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    objects = ActiveUserManager()
    all_objects = UserManager()

    def __str__(self):
        return f"{self.get_full_name() or self.email or self.pk}"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.save()
