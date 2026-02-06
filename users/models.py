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
    
    GENDER_CHOICES = (
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
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
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, null=True, blank=True)
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


class SystemSettings(models.Model):
    """
    System-wide settings for various features.
    Only one instance should exist (singleton pattern).
    """
    
    # Birthday Greeting Settings
    birthday_greeting_enabled = models.BooleanField(
        default=True,
        help_text="Enable/disable birthday greeting modal"
    )
    birthday_greeting_title = models.CharField(
        max_length=100,
        default="Happy Birthday!",
        help_text="Title for birthday greeting modal"
    )
    birthday_greeting_message = models.TextField(
        default="Wishing you a wonderful day filled with happiness and joy! Thank you for being part of our team.",
        help_text="Message shown in birthday greeting modal"
    )
    birthday_greeting_button_text = models.CharField(
        max_length=50,
        default="Thank You! 💝",
        help_text="Text shown on the dismiss button"
    )
    birthday_greeting_show_confetti = models.BooleanField(
        default=True,
        help_text="Show animated confetti on birthday greeting"
    )
    birthday_greeting_show_emojis = models.BooleanField(
        default=True,
        help_text="Show emoji decorations on birthday greeting"
    )
    birthday_greeting_male_emojis = models.CharField(
        max_length=200,
        default="🎈,🎊,🎁,🎉,🍺",
        help_text="Comma-separated list of emojis for male employees (e.g., 🎈,🎊,🎁,🎉,🍺)"
    )
    birthday_greeting_female_emojis = models.CharField(
        max_length=200,
        default="🎈,🎊,🎁,🎉,💐",
        help_text="Comma-separated list of emojis for female employees (e.g., 🎈,🎊,🎁,🎉,💐)"
    )
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "System Settings"
        verbose_name_plural = "System Settings"
    
    def save(self, *args, **kwargs):
        # Ensure only one instance exists (singleton)
        if not self.pk and SystemSettings.objects.exists():
            # Update existing instance instead of creating new one
            existing = SystemSettings.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)
    
    @classmethod
    def get_settings(cls):
        """Get or create system settings instance"""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings
    
    def __str__(self):
        return "System Settings"
