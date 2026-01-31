"""
Business logic for expense management system.

Handles:
- Expense creation and validation
- Approval workflow
- Category management
- Budget tracking
- Payment recording
- Expense analytics and reporting
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from inventory.models import Stall
from users.models import CustomUser

from expenses.models import (
    Expense,
    ExpenseBudget,
    ExpenseCategory,
    ExpenseItem,
)


# ================================
# Expense Manager
# ================================
class ExpenseManager:
    """
    Core expense operations: create, validate, update, delete
    """

    @staticmethod
    @transaction.atomic
    def create_expense(
        *,
        stall,
        category,
        expense_date,
        total_price,
        description='',
        vendor='',
        reference_number='',
        priority='medium',
        submitted_by,
        source='manual',
        items: List[Dict] = None,
        recurring=False,
        recurring_frequency=None,
    ) -> Expense:
        """
        Create a new expense with validation.

        Args:
            stall: Stall instance
            category: ExpenseCategory instance
            expense_date: Date of expense
            total_price: Total expense amount
            description: Expense description
            vendor: Vendor/supplier name
            reference_number: Invoice/receipt number
            priority: Priority level (low, medium, high, urgent)
            submitted_by: User creating the expense
            source: 'manual' or 'service'
            items: Optional list of expense items
            recurring: Is this a recurring expense
            recurring_frequency: Frequency if recurring

        Returns:
            Created Expense instance
        """
        # Validate inputs
        if total_price <= 0:
            raise ValidationError("Total price must be positive")

        if recurring and not recurring_frequency:
            raise ValidationError("Recurring frequency is required for recurring expenses")

        # Create expense
        expense = Expense.objects.create(
            stall=stall,
            category=category,
            expense_date=expense_date,
            total_price=total_price,
            description=description,
            vendor=vendor,
            reference_number=reference_number,
            priority=priority,
            submitted_by=submitted_by,
            created_by=submitted_by,
            source=source,
            recurring=recurring,
            recurring_frequency=recurring_frequency,
            approval_status=Expense.ApprovalStatus.PENDING,
            payment_status=Expense.PaymentStatus.UNPAID,
        )

        # Create expense items if provided
        if items:
            for item_data in items:
                ExpenseItem.objects.create(
                    expense=expense,
                    item=item_data.get('item'),
                    description=item_data.get('description', ''),
                    quantity=item_data.get('quantity', 1),
                    unit_price=item_data.get('unit_price', Decimal('0.00')),
                    total_price=item_data.get('quantity', 1) * item_data.get('unit_price', Decimal('0.00')),
                )

        return expense

    @staticmethod
    def update_expense(
        expense: Expense,
        **kwargs
    ) -> Expense:
        """
        Update an expense with validation.

        Args:
            expense: Expense instance to update
            **kwargs: Fields to update

        Returns:
            Updated Expense instance
        """
        # Prevent updates to paid or approved expenses
        if expense.payment_status == Expense.PaymentStatus.PAID:
            raise ValidationError("Cannot update a fully paid expense")

        if expense.approval_status == Expense.ApprovalStatus.APPROVED and 'approval_status' not in kwargs:
            raise ValidationError("Cannot update an approved expense without changing approval status")

        # Update allowed fields
        allowed_fields = [
            'category', 'expense_date', 'total_price', 'description',
            'vendor', 'reference_number', 'priority', 'recurring',
            'recurring_frequency'
        ]

        for field, value in kwargs.items():
            if field in allowed_fields:
                setattr(expense, field, value)

        expense.save()
        return expense

    @staticmethod
    def delete_expense(expense: Expense) -> None:
        """
        Soft delete an expense.

        Args:
            expense: Expense instance to delete
        """
        if expense.payment_status == Expense.PaymentStatus.PAID:
            raise ValidationError("Cannot delete a paid expense")

        if expense.approval_status == Expense.ApprovalStatus.APPROVED:
            raise ValidationError("Cannot delete an approved expense. Cancel it first.")

        expense.soft_delete()

    @staticmethod
    def get_expense_summary(expense: Expense) -> Dict:
        """
        Get comprehensive summary of an expense.

        Args:
            expense: Expense instance

        Returns:
            Dictionary with expense summary
        """
        return {
            'id': expense.id,
            'stall': expense.stall.name if expense.stall else None,
            'category': expense.category.name if expense.category else 'Uncategorized',
            'expense_date': expense.expense_date,
            'reference_number': expense.reference_number,
            'vendor': expense.vendor,
            'description': expense.description,
            'total_price': float(expense.total_price),
            'paid_amount': float(expense.paid_amount),
            'balance_due': float(expense.balance_due),
            'approval_status': expense.approval_status,
            'payment_status': expense.payment_status,
            'priority': expense.priority,
            'is_overdue': expense.is_overdue,
            'submitted_by': expense.submitted_by.get_full_name() if expense.submitted_by else None,
            'approved_by': expense.approved_by.get_full_name() if expense.approved_by else None,
            'approved_at': expense.approved_at,
            'items_count': expense.items.count(),
            'attachments_count': expense.attachments.count(),
            'created_at': expense.created_at,
        }


# ================================
# Expense Approval Workflow
# ================================
class ExpenseApprovalWorkflow:
    """
    Handles expense approval, rejection, and cancellation workflow
    """

    @staticmethod
    @transaction.atomic
    def approve_expense(
        expense: Expense,
        approved_by: CustomUser,
        notes: str = ''
    ) -> Expense:
        """
        Approve an expense.

        Args:
            expense: Expense to approve
            approved_by: User approving the expense
            notes: Optional approval notes

        Returns:
            Approved expense
        """
        if expense.approval_status == Expense.ApprovalStatus.APPROVED:
            raise ValidationError("Expense is already approved")

        if expense.approval_status == Expense.ApprovalStatus.CANCELLED:
            raise ValidationError("Cannot approve a cancelled expense")

        expense.approve(approved_by)

        # Add notes to description if provided
        if notes:
            expense.description = f"{expense.description}\n\nApproval Notes: {notes}"
            expense.save()

        return expense

    @staticmethod
    @transaction.atomic
    def reject_expense(
        expense: Expense,
        rejected_by: CustomUser,
        reason: str
    ) -> Expense:
        """
        Reject an expense.

        Args:
            expense: Expense to reject
            rejected_by: User rejecting the expense
            reason: Reason for rejection

        Returns:
            Rejected expense
        """
        if not reason:
            raise ValidationError("Rejection reason is required")

        if expense.approval_status == Expense.ApprovalStatus.APPROVED:
            raise ValidationError("Cannot reject an already approved expense")

        expense.reject(rejected_by, reason)
        return expense

    @staticmethod
    def cancel_expense(expense: Expense) -> Expense:
        """
        Cancel an expense.

        Args:
            expense: Expense to cancel

        Returns:
            Cancelled expense
        """
        expense.cancel()
        return expense

    @staticmethod
    def get_pending_approvals(stall=None) -> List[Expense]:
        """
        Get all expenses pending approval.

        Args:
            stall: Optional stall filter

        Returns:
            QuerySet of pending expenses
        """
        queryset = Expense.objects.filter(
            approval_status=Expense.ApprovalStatus.PENDING,
            is_deleted=False
        ).select_related(
            'stall', 'category', 'submitted_by'
        ).order_by('priority', '-expense_date')

        if stall:
            queryset = queryset.filter(stall=stall)

        return queryset

    @staticmethod
    def bulk_approve(
        expense_ids: List[int],
        approved_by: CustomUser
    ) -> Tuple[int, List[str]]:
        """
        Bulk approve multiple expenses.

        Args:
            expense_ids: List of expense IDs to approve
            approved_by: User approving the expenses

        Returns:
            Tuple of (approved_count, error_messages)
        """
        approved_count = 0
        errors = []

        for expense_id in expense_ids:
            try:
                expense = Expense.objects.get(id=expense_id, is_deleted=False)
                ExpenseApprovalWorkflow.approve_expense(expense, approved_by)
                approved_count += 1
            except Expense.DoesNotExist:
                errors.append(f"Expense {expense_id} not found")
            except ValidationError as e:
                errors.append(f"Expense {expense_id}: {str(e)}")

        return approved_count, errors


# ================================
# Expense Payment Handler
# ================================
class ExpensePaymentHandler:
    """
    Handles expense payment recording and tracking
    """

    @staticmethod
    @transaction.atomic
    def record_payment(
        expense: Expense,
        amount: Decimal,
        payment_method: str = 'cash',
        payment_date: datetime = None,
        notes: str = ''
    ) -> Expense:
        """
        Record a payment for an expense.

        Args:
            expense: Expense to record payment for
            amount: Payment amount
            payment_method: Payment method (cash, bank_transfer, etc)
            payment_date: Date of payment (defaults to now)
            notes: Optional payment notes

        Returns:
            Updated expense
        """
        if expense.approval_status != Expense.ApprovalStatus.APPROVED:
            raise ValidationError("Cannot pay an unapproved expense")

        if amount <= 0:
            raise ValidationError("Payment amount must be positive")

        if expense.paid_amount + amount > expense.total_price:
            raise ValidationError(
                f"Payment would exceed total expense. "
                f"Balance due: ₱{expense.balance_due}"
            )

        expense.record_payment(amount, payment_method, payment_date)

        if notes:
            expense.description = f"{expense.description}\n\nPayment Notes: {notes}"
            expense.save()

        return expense

    @staticmethod
    def get_unpaid_expenses(stall=None, days_overdue: int = None) -> List[Expense]:
        """
        Get unpaid or partially paid expenses.

        Args:
            stall: Optional stall filter
            days_overdue: Optional filter for overdue days

        Returns:
            QuerySet of unpaid expenses
        """
        queryset = Expense.objects.filter(
            Q(payment_status=Expense.PaymentStatus.UNPAID) |
            Q(payment_status=Expense.PaymentStatus.PARTIAL),
            is_deleted=False,
            approval_status=Expense.ApprovalStatus.APPROVED
        ).select_related('stall', 'category').order_by('expense_date')

        if stall:
            queryset = queryset.filter(stall=stall)

        if days_overdue is not None:
            cutoff_date = timezone.now().date() - timedelta(days=days_overdue)
            queryset = queryset.filter(expense_date__lte=cutoff_date)

        return queryset

    @staticmethod
    def get_payment_summary(start_date, end_date, stall=None) -> Dict:
        """
        Get payment summary for a period.

        Args:
            start_date: Start date
            end_date: End date
            stall: Optional stall filter

        Returns:
            Dictionary with payment summary
        """
        queryset = Expense.objects.filter(
            expense_date__gte=start_date,
            expense_date__lte=end_date,
            is_deleted=False
        )

        if stall:
            queryset = queryset.filter(stall=stall)

        summary = queryset.aggregate(
            total_expenses=Sum('total_price'),
            total_paid=Sum('paid_amount'),
            count=Count('id')
        )

        total_expenses = summary['total_expenses'] or Decimal('0.00')
        total_paid = summary['total_paid'] or Decimal('0.00')
        balance_due = total_expenses - total_paid

        # Status breakdown
        status_breakdown = queryset.values('payment_status').annotate(
            count=Count('id'),
            total=Sum('total_price')
        )

        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date,
            },
            'total_expenses': float(total_expenses),
            'total_paid': float(total_paid),
            'balance_due': float(balance_due),
            'expense_count': summary['count'] or 0,
            'payment_rate': float((total_paid / total_expenses * 100) if total_expenses > 0 else 0),
            'status_breakdown': [
                {
                    'status': item['payment_status'],
                    'count': item['count'],
                    'total': float(item['total'] or 0)
                }
                for item in status_breakdown
            ]
        }


# ================================
# Expense Category Manager
# ================================
class ExpenseCategoryManager:
    """
    Manages expense categories
    """

    @staticmethod
    def create_category(
        name: str,
        description: str = '',
        monthly_budget: Decimal = Decimal('0.00'),
        parent=None
    ) -> ExpenseCategory:
        """
        Create a new expense category.

        Args:
            name: Category name
            description: Category description
            monthly_budget: Default monthly budget
            parent: Parent category for hierarchical structure

        Returns:
            Created ExpenseCategory
        """
        if ExpenseCategory.objects.filter(name=name, is_deleted=False).exists():
            raise ValidationError(f"Category '{name}' already exists")

        category = ExpenseCategory.objects.create(
            name=name,
            description=description,
            monthly_budget=monthly_budget,
            parent=parent,
            is_active=True
        )

        return category

    @staticmethod
    def update_category(
        category: ExpenseCategory,
        **kwargs
    ) -> ExpenseCategory:
        """
        Update an expense category.

        Args:
            category: Category to update
            **kwargs: Fields to update

        Returns:
            Updated category
        """
        allowed_fields = ['name', 'description', 'monthly_budget', 'parent', 'is_active']

        for field, value in kwargs.items():
            if field in allowed_fields:
                setattr(category, field, value)

        category.save()
        return category

    @staticmethod
    def get_categories_with_stats(stall=None, month=None, year=None) -> List[Dict]:
        """
        Get categories with expense statistics.

        Args:
            stall: Optional stall filter
            month: Optional month filter
            year: Optional year filter

        Returns:
            List of categories with stats
        """
        categories = ExpenseCategory.objects.filter(
            is_deleted=False,
            is_active=True
        ).order_by('name')

        results = []
        for category in categories:
            # Build expense filter
            expense_filter = Q(category=category, is_deleted=False)

            if stall:
                expense_filter &= Q(stall=stall)

            if month and year:
                expense_filter &= Q(
                    expense_date__year=year,
                    expense_date__month=month
                )

            # Get expense stats
            stats = Expense.objects.filter(expense_filter).aggregate(
                total_expenses=Sum('total_price'),
                count=Count('id')
            )

            results.append({
                'id': category.id,
                'name': category.name,
                'full_path': category.get_full_path(),
                'description': category.description,
                'monthly_budget': float(category.monthly_budget),
                'total_expenses': float(stats['total_expenses'] or 0),
                'expense_count': stats['count'] or 0,
                'budget_utilization': float(
                    (stats['total_expenses'] or 0) / category.monthly_budget * 100
                    if category.monthly_budget > 0 else 0
                ),
                'has_subcategories': category.subcategories.filter(is_deleted=False).exists()
            })

        return results


# ================================
# Expense Budget Tracker
# ================================
class ExpenseBudgetTracker:
    """
    Tracks and manages expense budgets
    """

    @staticmethod
    @transaction.atomic
    def set_budget(
        stall: Stall,
        category: ExpenseCategory,
        month: int,
        year: int,
        budgeted_amount: Decimal,
        notes: str = ''
    ) -> ExpenseBudget:
        """
        Set budget for a category/period.

        Args:
            stall: Stall
            category: Expense category
            month: Month (1-12)
            year: Year
            budgeted_amount: Budget amount
            notes: Optional notes

        Returns:
            Created or updated ExpenseBudget
        """
        if month < 1 or month > 12:
            raise ValidationError("Month must be between 1 and 12")

        if budgeted_amount < 0:
            raise ValidationError("Budget amount cannot be negative")

        budget, created = ExpenseBudget.objects.update_or_create(
            stall=stall,
            category=category,
            month=month,
            year=year,
            defaults={
                'budgeted_amount': budgeted_amount,
                'notes': notes,
                'is_deleted': False
            }
        )

        return budget

    @staticmethod
    def get_budget_status(
        stall: Stall,
        month: int,
        year: int
    ) -> List[Dict]:
        """
        Get budget status for all categories in a period.

        Args:
            stall: Stall
            month: Month
            year: Year

        Returns:
            List of budget status dictionaries
        """
        budgets = ExpenseBudget.objects.filter(
            stall=stall,
            month=month,
            year=year,
            is_deleted=False
        ).select_related('category')

        results = []
        for budget in budgets:
            results.append({
                'category': budget.category.name,
                'budgeted_amount': float(budget.budgeted_amount),
                'actual_expenses': float(budget.actual_expenses),
                'variance': float(budget.variance),
                'utilization_percentage': float(budget.utilization_percentage),
                'status': 'over_budget' if budget.variance < 0 else 'within_budget'
            })

        return results

    @staticmethod
    def get_budget_alerts(stall=None, threshold_percentage: float = 90.0) -> List[Dict]:
        """
        Get budget alerts for categories approaching or exceeding budget.

        Args:
            stall: Optional stall filter
            threshold_percentage: Alert when utilization exceeds this percentage

        Returns:
            List of budget alerts
        """
        now = timezone.now()
        current_month = now.month
        current_year = now.year

        budgets_query = ExpenseBudget.objects.filter(
            month=current_month,
            year=current_year,
            is_deleted=False
        ).select_related('category', 'stall')

        if stall:
            budgets_query = budgets_query.filter(stall=stall)

        alerts = []
        for budget in budgets_query:
            utilization = budget.utilization_percentage
            if utilization >= threshold_percentage:
                alerts.append({
                    'stall': budget.stall.name,
                    'category': budget.category.name,
                    'budgeted_amount': float(budget.budgeted_amount),
                    'actual_expenses': float(budget.actual_expenses),
                    'utilization_percentage': float(utilization),
                    'variance': float(budget.variance),
                    'alert_level': 'critical' if utilization > 100 else 'warning'
                })

        return sorted(alerts, key=lambda x: x['utilization_percentage'], reverse=True)


# ================================
# Expense Analytics
# ================================
class ExpenseAnalytics:
    """
    Analytics and reporting for expenses
    """

    @staticmethod
    def get_expense_summary(
        start_date,
        end_date,
        stall=None,
        category=None
    ) -> Dict:
        """
        Get comprehensive expense summary for a period.

        Args:
            start_date: Start date
            end_date: End date
            stall: Optional stall filter
            category: Optional category filter

        Returns:
            Dictionary with expense summary
        """
        queryset = Expense.objects.filter(
            expense_date__gte=start_date,
            expense_date__lte=end_date,
            is_deleted=False
        )

        if stall:
            queryset = queryset.filter(stall=stall)

        if category:
            queryset = queryset.filter(category=category)

        # Aggregate data
        summary = queryset.aggregate(
            total_expenses=Sum('total_price'),
            total_paid=Sum('paid_amount'),
            count=Count('id'),
            avg_expense=Avg('total_price')
        )

        # Breakdown by category
        category_breakdown = queryset.values(
            'category__name'
        ).annotate(
            total=Sum('total_price'),
            count=Count('id')
        ).order_by('-total')

        # Breakdown by approval status
        approval_breakdown = queryset.values(
            'approval_status'
        ).annotate(
            count=Count('id'),
            total=Sum('total_price')
        )

        # Breakdown by payment status
        payment_breakdown = queryset.values(
            'payment_status'
        ).annotate(
            count=Count('id'),
            total=Sum('total_price')
        )

        total_expenses = summary['total_expenses'] or Decimal('0.00')
        total_paid = summary['total_paid'] or Decimal('0.00')

        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date,
            },
            'summary': {
                'total_expenses': float(total_expenses),
                'total_paid': float(total_paid),
                'balance_due': float(total_expenses - total_paid),
                'expense_count': summary['count'] or 0,
                'average_expense': float(summary['avg_expense'] or 0),
            },
            'category_breakdown': [
                {
                    'category': item['category__name'] or 'Uncategorized',
                    'total': float(item['total']),
                    'count': item['count'],
                    'percentage': float(item['total'] / total_expenses * 100) if total_expenses > 0 else 0
                }
                for item in category_breakdown
            ],
            'approval_breakdown': [
                {
                    'status': item['approval_status'],
                    'count': item['count'],
                    'total': float(item['total'] or 0)
                }
                for item in approval_breakdown
            ],
            'payment_breakdown': [
                {
                    'status': item['payment_status'],
                    'count': item['count'],
                    'total': float(item['total'] or 0)
                }
                for item in payment_breakdown
            ]
        }

    @staticmethod
    def get_expense_trends(
        start_date,
        end_date,
        stall=None,
        category=None,
        interval='month'
    ) -> List[Dict]:
        """
        Get expense trends over time.

        Args:
            start_date: Start date
            end_date: End date
            stall: Optional stall filter
            category: Optional category filter
            interval: 'day', 'week', or 'month'

        Returns:
            List of trend data points
        """
        from django.db.models.functions import TruncDay, TruncMonth, TruncWeek

        queryset = Expense.objects.filter(
            expense_date__gte=start_date,
            expense_date__lte=end_date,
            is_deleted=False
        )

        if stall:
            queryset = queryset.filter(stall=stall)

        if category:
            queryset = queryset.filter(category=category)

        # Choose truncation based on interval
        if interval == 'day':
            trunc_func = TruncDay
        elif interval == 'week':
            trunc_func = TruncWeek
        else:
            trunc_func = TruncMonth

        trends = queryset.annotate(
            period=trunc_func('expense_date')
        ).values('period').annotate(
            total_expenses=Sum('total_price'),
            count=Count('id')
        ).order_by('period')

        return [
            {
                'period': item['period'].strftime('%Y-%m-%d'),
                'total_expenses': float(item['total_expenses']),
                'expense_count': item['count']
            }
            for item in trends
        ]

    @staticmethod
    def get_top_vendors(
        start_date,
        end_date,
        stall=None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get top vendors by expense amount.

        Args:
            start_date: Start date
            end_date: End date
            stall: Optional stall filter
            limit: Number of vendors to return

        Returns:
            List of top vendors
        """
        queryset = Expense.objects.filter(
            expense_date__gte=start_date,
            expense_date__lte=end_date,
            is_deleted=False,
            vendor__isnull=False
        ).exclude(vendor='')

        if stall:
            queryset = queryset.filter(stall=stall)

        vendors = queryset.values('vendor').annotate(
            total_expenses=Sum('total_price'),
            count=Count('id')
        ).order_by('-total_expenses')[:limit]

        return [
            {
                'vendor': item['vendor'],
                'total_expenses': float(item['total_expenses']),
                'expense_count': item['count']
            }
            for item in vendors
        ]

    @staticmethod
    def get_expense_comparison(
        current_start,
        current_end,
        previous_start,
        previous_end,
        stall=None
    ) -> Dict:
        """
        Compare expenses between two periods.

        Args:
            current_start: Current period start date
            current_end: Current period end date
            previous_start: Previous period start date
            previous_end: Previous period end date
            stall: Optional stall filter

        Returns:
            Comparison data
        """
        def get_period_data(start, end):
            queryset = Expense.objects.filter(
                expense_date__gte=start,
                expense_date__lte=end,
                is_deleted=False
            )
            if stall:
                queryset = queryset.filter(stall=stall)

            return queryset.aggregate(
                total=Sum('total_price'),
                count=Count('id')
            )

        current_data = get_period_data(current_start, current_end)
        previous_data = get_period_data(previous_start, previous_end)

        current_total = current_data['total'] or Decimal('0.00')
        previous_total = previous_data['total'] or Decimal('0.00')

        change = current_total - previous_total
        change_percentage = (
            (change / previous_total * 100) if previous_total > 0 else 0
        )

        return {
            'current_period': {
                'start_date': current_start,
                'end_date': current_end,
                'total_expenses': float(current_total),
                'expense_count': current_data['count'] or 0,
            },
            'previous_period': {
                'start_date': previous_start,
                'end_date': previous_end,
                'total_expenses': float(previous_total),
                'expense_count': previous_data['count'] or 0,
            },
            'comparison': {
                'change': float(change),
                'change_percentage': float(change_percentage),
                'trend': 'up' if change > 0 else 'down' if change < 0 else 'stable'
            }
        }
