"""
Enhanced filters for expense management system.

Provides filtering for:
- Expense categories
- Payment status
- Date ranges
- Vendors
- Stalls
"""

from django_filters import rest_framework as filters
from expenses.models import Expense, ExpenseCategory


class ExpenseFilter(filters.FilterSet):
    """
    Comprehensive filter for expenses with multiple criteria
    """

    # Category filtering
    category = filters.ModelChoiceFilter(queryset=ExpenseCategory.objects.filter(is_deleted=False))
    category_name = filters.CharFilter(field_name='category__name', lookup_expr='icontains')

    # Date filtering
    expense_date = filters.DateFilter()
    expense_date__gte = filters.DateFilter(field_name='expense_date', lookup_expr='gte')
    expense_date__lte = filters.DateFilter(field_name='expense_date', lookup_expr='lte')
    start_date = filters.DateFilter(field_name='expense_date', lookup_expr='gte')
    end_date = filters.DateFilter(field_name='expense_date', lookup_expr='lte')

    # Payment filtering
    payment_status = filters.ChoiceFilter(choices=Expense.PaymentStatus.choices)
    is_paid = filters.BooleanFilter(method='filter_is_paid')
    is_unpaid = filters.BooleanFilter(method='filter_is_unpaid')

    # Vendor filtering
    vendor = filters.CharFilter(lookup_expr='icontains')
    vendor_exact = filters.CharFilter(field_name='vendor', lookup_expr='iexact')

    # Reference filtering
    reference_number = filters.CharFilter(lookup_expr='icontains')

    # Amount filtering
    total_price__gte = filters.NumberFilter(field_name='total_price', lookup_expr='gte')
    total_price__lte = filters.NumberFilter(field_name='total_price', lookup_expr='lte')

    # Stall filtering
    stall = filters.NumberFilter()
    stall__isnull = filters.BooleanFilter(field_name='stall', lookup_expr='isnull')

    # Source filtering
    source = filters.ChoiceFilter(choices=[('manual', 'Manual'), ('service', 'Service')])

    # Overdue filter
    is_overdue = filters.BooleanFilter(method='filter_is_overdue')

    class Meta:
        model = Expense
        fields = [
            'stall',
            'category',
            'payment_status',
            'source',
            'expense_date',
        ]

    def filter_is_paid(self, queryset, name, value):
        """Filter for fully paid expenses"""
        if value:
            return queryset.filter(payment_status=Expense.PaymentStatus.PAID)
        return queryset.exclude(payment_status=Expense.PaymentStatus.PAID)

    def filter_is_unpaid(self, queryset, name, value):
        """Filter for unpaid or partially paid expenses"""
        if value:
            return queryset.filter(
                payment_status__in=[
                    Expense.PaymentStatus.UNPAID,
                    Expense.PaymentStatus.PARTIAL
                ]
            )
        return queryset.filter(payment_status=Expense.PaymentStatus.PAID)

    def filter_is_overdue(self, queryset, name, value):
        """Filter for overdue expenses (unpaid for >30 days)"""
        from datetime import timedelta

        from django.utils import timezone

        cutoff_date = timezone.now().date() - timedelta(days=30)

        if value:
            return queryset.filter(
                expense_date__lte=cutoff_date
            ).exclude(payment_status=Expense.PaymentStatus.PAID)
        return queryset.filter(
            expense_date__gt=cutoff_date
        ) | queryset.filter(payment_status=Expense.PaymentStatus.PAID)


class ExpenseCategoryFilter(filters.FilterSet):
    """
    Filter for expense categories
    """

    # Name filtering
    name = filters.CharFilter(lookup_expr='icontains')

    # Parent filtering
    parent = filters.NumberFilter()
    parent__isnull = filters.BooleanFilter(field_name='parent', lookup_expr='isnull')

    # Status filtering
    is_active = filters.BooleanFilter()

    class Meta:
        model = ExpenseCategory
        fields = ['name', 'parent', 'is_active']
