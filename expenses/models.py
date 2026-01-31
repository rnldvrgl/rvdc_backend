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


class ExpenseBudget(models.Model):
    """
    Monthly or periodic budget tracking for expense categories per stall
    """
    stall = models.ForeignKey(
        "inventory.Stall",
        on_delete=models.CASCADE,
        related_name="expense_budgets"
    )
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.CASCADE,
        related_name="budgets"
    )

    # Budget period
    month = models.PositiveSmallIntegerField(
        help_text="Month (1-12)"
    )
    year = models.PositiveIntegerField(
        help_text="Year"
    )

    # Budget amounts
    budgeted_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Budgeted amount for this period"
    )

    # Tracking
    notes = models.TextField(blank=True)
    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Expense Budget"
        verbose_name_plural = "Expense Budgets"
        unique_together = ('stall', 'category', 'month', 'year')
        ordering = ['-year', '-month', 'category__name']
        indexes = [
            models.Index(fields=['stall', 'year', 'month']),
            models.Index(fields=['category', 'year', 'month']),
        ]

    def __str__(self):
        return f"{self.category.name} - {self.year}/{self.month:02d} - {self.stall.name}"

    def clean(self):
        if self.month < 1 or self.month > 12:
            raise ValidationError({'month': 'Month must be between 1 and 12'})

        if self.year < 2000:
            raise ValidationError({'year': 'Year must be 2000 or later'})

    @property
    def actual_expenses(self):
        """Calculate actual expenses for this budget period"""
        from django.db.models import Sum

        start_date = timezone.datetime(self.year, self.month, 1).date()

        # Calculate end date (last day of month)
        if self.month == 12:
            end_date = timezone.datetime(self.year, 12, 31).date()
        else:
            end_date = (timezone.datetime(self.year, self.month + 1, 1) - timezone.timedelta(days=1)).date()

        total = Expense.objects.filter(
            stall=self.stall,
            category=self.category,
            is_deleted=False,
            expense_date__gte=start_date,
            expense_date__lte=end_date
        ).aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')

        return total

    @property
    def variance(self):
        """Budget variance (positive = under budget, negative = over budget)"""
        return self.budgeted_amount - self.actual_expenses

    @property
    def utilization_percentage(self):
        """Budget utilization as percentage"""
        if self.budgeted_amount == 0:
            return Decimal('0.00')
        return (self.actual_expenses / self.budgeted_amount) * 100


class Expense(models.Model):
    """
    Enhanced expense tracking with categories, approval workflow, and attachments
    """

    # Approval status choices
    class ApprovalStatus(models.TextChoices):
        PENDING = 'pending', _('Pending Approval')
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
        CANCELLED = 'cancelled', _('Cancelled')

    # Payment status choices
    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', _('Unpaid')
        PARTIAL = 'partial', _('Partially Paid')
        PAID = 'paid', _('Fully Paid')

    # Priority choices
    class Priority(models.TextChoices):
        LOW = 'low', _('Low')
        MEDIUM = 'medium', _('Medium')
        HIGH = 'high', _('High')
        URGENT = 'urgent', _('Urgent')

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
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM
    )

    # Payment tracking
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(
        max_length=50,
        blank=True,
        help_text="Cash, Bank Transfer, Cheque, etc."
    )

    # Approval workflow
    submitted_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="submitted_expenses",
        help_text="User who submitted the expense"
    )
    approved_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_expenses",
        help_text="User who approved the expense"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection if applicable"
    )

    # Additional tracking
    source = models.CharField(
        max_length=20,
        choices=[("manual", "Manual"), ("service", "Service")],
        default="manual",
    )
    recurring = models.BooleanField(
        default=False,
        help_text="Is this a recurring expense?"
    )
    recurring_frequency = models.CharField(
        max_length=20,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('yearly', 'Yearly'),
        ],
        blank=True,
        null=True
    )

    # Legacy field compatibility
    created_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_expenses_legacy"
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
            models.Index(fields=['approval_status', 'expense_date']),
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

        if self.recurring and not self.recurring_frequency:
            raise ValidationError({
                'recurring_frequency': 'Frequency is required for recurring expenses'
            })

        if self.approval_status == self.ApprovalStatus.REJECTED and not self.rejection_reason:
            raise ValidationError({
                'rejection_reason': 'Rejection reason is required when rejecting an expense'
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

        # Set submitted_by if not set
        if not self.submitted_by and self.created_by:
            self.submitted_by = self.created_by

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

    @property
    def is_pending_approval(self):
        """Check if expense is pending approval"""
        return self.approval_status == self.ApprovalStatus.PENDING

    @property
    def is_approved(self):
        """Check if expense is approved"""
        return self.approval_status == self.ApprovalStatus.APPROVED

    def approve(self, approved_by_user):
        """Approve the expense"""
        if self.approval_status == self.ApprovalStatus.APPROVED:
            raise ValidationError("Expense is already approved")

        self.approval_status = self.ApprovalStatus.APPROVED
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.rejection_reason = ""
        self.save()

    def reject(self, rejected_by_user, reason):
        """Reject the expense"""
        if self.approval_status == self.ApprovalStatus.REJECTED:
            raise ValidationError("Expense is already rejected")

        if not reason:
            raise ValidationError("Rejection reason is required")

        self.approval_status = self.ApprovalStatus.REJECTED
        self.approved_by = rejected_by_user
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        self.save()

    def cancel(self):
        """Cancel the expense"""
        if self.payment_status == self.PaymentStatus.PAID:
            raise ValidationError("Cannot cancel a paid expense")

        self.approval_status = self.ApprovalStatus.CANCELLED
        self.save()

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


class ExpenseAttachment(models.Model):
    """
    Attachments for expenses (receipts, invoices, etc.)
    """
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name="attachments"
    )
    file = models.FileField(
        upload_to='expenses/attachments/%Y/%m/',
        help_text="Upload receipt, invoice, or supporting document"
    )
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50, blank=True)
    file_size = models.PositiveIntegerField(
        help_text="File size in bytes",
        null=True,
        blank=True
    )
    description = models.CharField(max_length=255, blank=True)

    uploaded_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Expense Attachment"
        verbose_name_plural = "Expense Attachments"
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.filename} - {self.expense}"

    def save(self, *args, **kwargs):
        if self.file:
            self.filename = self.file.name
            self.file_size = self.file.size
        super().save(*args, **kwargs)
