from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.models import UserManager
from django.utils import timezone
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
    e_signature = models.ImageField(
        upload_to="e_signatures/",
        null=True,
        blank=True,
    )
    sss_number = models.CharField(max_length=50, blank=True, null=True)
    philhealth_number = models.CharField(max_length=50, blank=True, null=True)
    tin_number = models.CharField(max_length=50, blank=True, null=True)
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    cash_ban_balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Employee's cash ban fund balance (accumulated fund that can be received at year-end or cash advanced)"
    )
    include_in_payroll = models.BooleanField(
        default=True,
        help_text="Include this employee in payroll generation"
    )

    # Individual government benefit flags for selective application
    has_sss = models.BooleanField(
        default=True,
        help_text="Apply SSS (Social Security System) deductions"
    )
    has_philhealth = models.BooleanField(
        default=True,
        help_text="Apply PhilHealth deductions"
    )
    has_pagibig = models.BooleanField(
        default=True,
        help_text="Apply Pag-IBIG (HDMF) deductions"
    )
    has_bir_tax = models.BooleanField(
        default=True,
        help_text="Apply BIR withholding tax deductions"
    )
    has_cash_ban = models.BooleanField(
        default=True,
        help_text="Include employee in cash ban fund contributions"
    )

    is_technician = models.BooleanField(
        default=False,
        help_text="Allow this employee to be assigned as a technician in service jobs regardless of their role"
    )

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    objects = ActiveUserManager()
    all_objects = UserManager()

    def __str__(self):
        return f"{self.get_full_name() or self.email or self.pk}"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def delete(self, *args, **kwargs):
        if kwargs.pop("force", False):
            super().delete(*args, **kwargs)
        else:
            self.is_deleted = True
            self.is_active = False
            self.deleted_at = timezone.now()
            self.save(update_fields=["is_deleted", "is_active", "deleted_at"])


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

    VARIANT_CHOICES = [
        ('default', 'Default'),
        ('minimalist', 'Modern Minimalist'),
        ('celebration', 'Celebration Theme'),
        ('elegant', 'Elegant Professional'),
        ('playful', 'Playful & Fun'),
    ]

    birthday_greeting_variant = models.CharField(
        max_length=20,
        choices=VARIANT_CHOICES,
        default='default',
        help_text="Design variant for birthday greeting card"
    )

    # Business Operations
    maintenance_mode = models.BooleanField(
        default=False,
        help_text="Enable maintenance mode — non-admin users will see the maintenance screen"
    )
    check_stock_on_sale = models.BooleanField(
        default=True,
        help_text="Check and deduct stock when creating or editing a sales transaction"
    )

    # Notification Settings
    notification_sound = models.CharField(
        max_length=255,
        default="",
        blank=True,
        help_text="Sound file path for push notifications (e.g., /sounds/notification.mp3)"
    )

    # Google Sheets Sync Settings (Sub-stall sales)
    google_sheets_sync_enabled = models.BooleanField(
        default=False,
        help_text="Enable automatic sync of sub-stall sales transactions to Google Sheets"
    )
    google_sheets_spreadsheet_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Google Spreadsheet ID from the sheet URL"
    )
    google_sheets_worksheet_name = models.CharField(
        max_length=100,
        blank=True,
        default="Sub Stall Sales",
        help_text="Worksheet/tab name where synced rows are written"
    )
    google_sheets_sub_stall_type = models.CharField(
        max_length=10,
        default="sub",
        blank=True,
        help_text="Only transactions from this stall_type are synced (sub for parts, main for services)"
    )
    google_service_account_json = models.TextField(
        blank=True,
        default="",
        help_text="Service account JSON credentials content used for Google Sheets API"
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


class CashAdvanceMovement(models.Model):
    """
    Tracks all movements (credits and debits) to an employee's cash ban balance.

    Movement types:
    - CREDIT (+): Adds to cash ban balance
      Examples: payroll cash ban deduction, manual addition, initial balance setup
    - DEBIT (-): Deducts from cash ban balance
      Examples: cash advance taken by employee

    Each movement updates the employee's cash_ban_balance and records
    a snapshot of the balance after the movement for audit trail.
    """

    class MovementType(models.TextChoices):
        CREDIT = 'credit', 'Credit (+)'
        DEBIT = 'debit', 'Debit (-)'

    employee = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='cash_advance_movements',
        help_text="Employee whose cash ban balance is affected"
    )
    movement_type = models.CharField(
        max_length=10,
        choices=MovementType.choices,
        help_text="Credit (+) adds to balance, Debit (-) deducts from balance"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount of the movement (always positive, sign determined by movement_type)"
    )
    balance_after = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Snapshot of the employee's cash ban balance after this movement"
    )
    date = models.DateField(
        help_text="Date of the movement"
    )
    description = models.TextField(
        blank=True,
        help_text="Notes or reason for the movement (e.g., 'Initial cash ban balance', 'Cash advance for personal use')"
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional reference (e.g., 'payroll-123', 'manual')"
    )
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_cash_advance_movements',
        help_text="User who recorded this movement"
    )
    is_pending = models.BooleanField(
        default=False,
        help_text="If True, movement is pending (linked to draft payroll) and not yet applied to balance"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['employee', 'date']),
            models.Index(fields=['-date']),
            models.Index(fields=['employee', 'movement_type']),
        ]

    def __str__(self):
        sign = '+' if self.movement_type == self.MovementType.CREDIT else '-'
        return f"Cash Ban {sign}₱{self.amount} - {self.employee.get_full_name()} ({self.date})"

    def save(self, *args, **kwargs):
        """Update employee's cash_ban_balance and record balance snapshot (only if not pending)."""
        is_new = self.pk is None
        if is_new:
            if not self.is_pending:
                # Apply to balance and record final balance after movement
                if self.movement_type == self.MovementType.CREDIT:
                    self.employee.cash_ban_balance += self.amount
                else:
                    self.employee.cash_ban_balance -= self.amount
                self.employee.save(update_fields=['cash_ban_balance'])
                self.balance_after = self.employee.cash_ban_balance
            else:
                # For pending movements, record current balance (before movement)
                # This will be updated to the actual balance after when applied
                self.balance_after = self.employee.cash_ban_balance
        super().save(*args, **kwargs)

    def apply_to_balance(self):
        """Apply this pending movement to the employee's balance."""
        if not self.is_pending:
            return  # Already applied

        if self.movement_type == self.MovementType.CREDIT:
            self.employee.cash_ban_balance += self.amount
        else:
            self.employee.cash_ban_balance -= self.amount
        self.employee.save(update_fields=['cash_ban_balance'])
        self.balance_after = self.employee.cash_ban_balance
        self.is_pending = False
        self.save(update_fields=['balance_after', 'is_pending'])
