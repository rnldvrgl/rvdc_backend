from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ExpenseCategory(models.Model):
    """
    Categories for organizing expenses (utilities, supplies, maintenance, etc.)
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Budget tracking
    monthly_budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Monthly budget allocated for this category"
    )

    # Parent category for hierarchical structure (optional)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subcategories'
    )

    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Expense Category"
        verbose_name_plural = "Expense Categories"
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active', 'is_deleted']),
        ]

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    def get_full_path(self):
        """Returns full hierarchical path of category"""
        if self.parent:
            return f"{self.parent.get_full_path()} > {self.name}"
        return self.name

    def get_total_budget(self):
        """Get total budget including subcategories"""
        total = self.monthly_budget
        for subcategory in self.subcategories.filter(is_active=True, is_deleted=False):
            total += subcategory.get_total_budget()
        return total

    def soft_delete(self):
        """Soft delete category"""
        self.is_deleted = True
        self.is_active = False
        self.save()





class Expense(models.Model):
    """
    Enhanced expense tracking with categories and payment tracking
    """

    # Payment status choices
    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', _('Unpaid')
        PARTIAL = 'partial', _('Partially Paid')
        PAID = 'paid', _('Fully Paid')

    # Basic information
    stall = models.ForeignKey(
        "inventory.Stall",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses",
        null=True,
        blank=True,
        help_text="Expense category for organization and budgeting"
    )

    # Expense details
    expense_date = models.DateField(
        default=timezone.now,
        help_text="Date when expense was incurred"
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Invoice number, receipt number, or other reference"
    )
    vendor = models.CharField(
        max_length=255,
        blank=True,
        help_text="Vendor or supplier name"
    )
    description = models.TextField(blank=True)

    # Financial details
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Status tracking
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID
    )

    # Payment tracking
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(
        max_length=50,
        default='cash',
        blank=True,
        help_text="Cash, Bank Transfer, Cheque, etc."
    )



    # Additional tracking
    source = models.CharField(
        max_length=20,
        choices=[("manual", "Manual"), ("service", "Service")],
        default="manual",
    )

    # User tracking
    created_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_expenses"
    )
    is_paid = models.BooleanField(default=False)

    # Soft delete
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        ordering = ['-expense_date', '-created_at']
        indexes = [
            models.Index(fields=['stall', 'expense_date']),
            models.Index(fields=['category', 'expense_date']),
            models.Index(fields=['payment_status', 'expense_date']),
            models.Index(fields=['is_deleted']),
        ]

    def __str__(self):
        category_name = self.category.name if self.category else "Uncategorized"
        return f"{category_name} - {self.expense_date} - ₱{self.total_price}"

    def clean(self):
        """Validate expense data"""
        super().clean()

        if self.paid_amount > self.total_price:
            raise ValidationError({
                'paid_amount': 'Paid amount cannot exceed total price'
            })

    def save(self, *args, **kwargs):
        # Auto-update payment status based on paid amount
        if self.paid_amount == 0:
            self.payment_status = self.PaymentStatus.UNPAID
            self.is_paid = False
        elif self.paid_amount >= self.total_price:
            self.payment_status = self.PaymentStatus.PAID
            self.is_paid = True
            if not self.paid_at:
                self.paid_at = timezone.now()
        else:
            self.payment_status = self.PaymentStatus.PARTIAL
            self.is_paid = False

        super().save(*args, **kwargs)

    @property
    def balance_due(self):
        """Amount still owed"""
        return max(self.total_price - self.paid_amount, Decimal('0.00'))

    @property
    def is_overdue(self):
        """Check if expense is overdue (unpaid and past due date)"""
        if self.payment_status == self.PaymentStatus.PAID:
            return False
        # Consider expense overdue if not paid within 30 days
        return (timezone.now().date() - self.expense_date).days > 30

    def record_payment(self, amount, payment_method='', payment_date=None):
        """Record a payment for this expense"""
        if amount <= 0:
            raise ValidationError("Payment amount must be positive")

        if self.paid_amount + amount > self.total_price:
            raise ValidationError("Payment would exceed total expense amount")

        self.paid_amount += amount
        self.payment_method = payment_method or self.payment_method

        if payment_date:
            self.paid_at = payment_date
        elif not self.paid_at:
            self.paid_at = timezone.now()

        self.save()

    def soft_delete(self):
        """Soft delete the expense"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()


class ExpenseItem(models.Model):
    """
    Line items for expenses (optional - for expenses with multiple items/services)
    """
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name="items"
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Link to inventory item if applicable"
    )

    description = models.CharField(
        max_length=255,
        help_text="Description of the expense item"
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Expense Item"
        verbose_name_plural = "Expense Items"
        ordering = ['id']

    def __str__(self):
        return f"{self.description} - {self.quantity} x ₱{self.unit_price}"

    def clean(self):
        """Validate expense item"""
        if self.expense.paid_amount > 0:
            raise ValidationError("Cannot edit items after payments have been made.")

        # Auto-calculate total_price if not set
        calculated_total = self.quantity * self.unit_price
        if self.total_price and self.total_price != calculated_total:
            raise ValidationError("Total price does not match quantity × unit price")

    def save(self, *args, **kwargs):
        # Auto-set description from item if not provided
        if self.item and not self.description:
            self.description = self.item.name

        # Auto-calculate total_price
        if not self.total_price:
            self.total_price = self.quantity * self.unit_price

        super().save(*args, **kwargs)
