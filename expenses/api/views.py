"""
API views for enhanced expense management system.

Provides endpoints for:
- Expense categories (CRUD, stats)
- Expenses (CRUD, payment recording, filtering)
- Expense analytics and reporting
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from expenses.api.filters import ExpenseFilter
from expenses.api.serializers import (
    ExpenseCategoryListSerializer,
    ExpenseCategorySerializer,
    ExpenseListSerializer,
    ExpensePaymentSerializer,
    ExpenseSerializer,
)
from expenses.business_logic import (
    ExpenseAnalytics,
    ExpenseCategoryManager,
    ExpenseManager,
    ExpensePaymentHandler,
)
from expenses.models import Expense, ExpenseCategory
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.filters.options import get_stall_options
from utils.filters.role_filters import get_role_based_filter_response
from utils.query import get_role_filtered_queryset
from utils.soft_delete import SoftDeleteViewSetMixin


# ================================
# Expense Category ViewSet
# ================================
class ExpenseCategoryViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for expense categories.

    Provides:
    - CRUD operations for categories
    - Hierarchical category support
    - Category statistics
    """
    queryset = ExpenseCategory.objects.filter(is_deleted=False)
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'list':
            return ExpenseCategoryListSerializer
        return ExpenseCategorySerializer

    def perform_destroy(self, instance):
        """Soft delete category"""
        instance.soft_delete()

    @action(detail=False, methods=['get'])
    def with_stats(self, request):
        """
        Get categories with expense statistics.

        Query params:
        - stall: Stall ID (optional)
        - month: Month (1-12, optional)
        - year: Year (optional)
        """
        stall_id = request.query_params.get('stall')
        month = request.query_params.get('month')
        year = request.query_params.get('year')

        # Convert to integers if provided
        stall = None
        if stall_id:
            from inventory.models import Stall
            try:
                stall = Stall.objects.get(id=stall_id)
            except Stall.DoesNotExist:
                pass

        month_int = int(month) if month else None
        year_int = int(year) if year else None

        categories_stats = ExpenseCategoryManager.get_categories_with_stats(
            stall=stall,
            month=month_int,
            year=year_int
        )

        return Response(categories_stats)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a category"""
        category = self.get_object()
        category.is_active = True
        category.save()
        serializer = self.get_serializer(category)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a category"""
        category = self.get_object()
        category.is_active = False
        category.save()
        serializer = self.get_serializer(category)
        return Response(serializer.data)


# ================================
# Expense ViewSet
# ================================
class ExpenseViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for expenses.

    Provides:
    - CRUD operations for expenses
    - Payment recording
    - Advanced filtering and search
    - Expense summaries
    """
    queryset = Expense.objects.select_related(
        'stall', 'category__parent', 'created_by'
    ).prefetch_related('items__item')
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ExpenseFilter
    search_fields = ['description', 'vendor', 'reference_number']
    ordering_fields = [
        'expense_date',
        'created_at',
        'total_price',
        'paid_amount',
        'paid_at',
    ]
    ordering = ['-expense_date', '-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ExpenseListSerializer
        return ExpenseSerializer

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_deleted=False)
        return get_role_filtered_queryset(self.request, queryset)

    def perform_create(self, serializer):
        """Create expense with user tracking"""
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        """Block updates when remittance is already remitted"""
        instance = serializer.instance
        if instance.stall:
            from remittances.models import RemittanceRecord
            if RemittanceRecord.objects.filter(
                stall=instance.stall,
                remittance_date=instance.expense_date,
                is_remitted=True,
            ).exists():
                raise DRFValidationError(
                    "Cannot update an expense that belongs to an already remitted record"
                )
        serializer.save()

    def perform_destroy(self, instance):
        """Soft delete expense"""
        try:
            ExpenseManager.delete_expense(instance)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)

    @action(detail=False, methods=['get'], url_path='filters')
    def get_filters(self, request):
        """Get available filter options"""
        filters_config = {
            'stall': {
                'options': get_stall_options,
                'exclude_for': ['clerk', 'manager'],
            },
            'category': {
                'options': lambda: [
                    {
                        'label': cat.name,
                        'value': str(cat.id)
                    }
                    for cat in ExpenseCategory.objects.filter(
                        is_deleted=False,
                        is_active=True
                    ).order_by('name')
                ]
            },
            'payment_status': {
                'options': lambda: [
                    {'label': 'Unpaid', 'value': 'unpaid'},
                    {'label': 'Partially Paid', 'value': 'partial'},
                    {'label': 'Fully Paid', 'value': 'paid'},
                ]
            },
            'source': {
                'options': lambda: [
                    {'label': 'Manual', 'value': 'manual'},
                    {'label': 'Service', 'value': 'service'},
                ]
            },
        }

        ordering_config = [
            {'label': 'Expense Date', 'value': 'expense_date'},
            {'label': 'Created At', 'value': 'created_at'},
            {'label': 'Total Price', 'value': 'total_price'},
            {'label': 'Paid Amount', 'value': 'paid_amount'},
        ]

        return get_role_based_filter_response(
            request,
            filters_config,
            ordering_config
        )

    @action(detail=True, methods=['post'], url_path='record-payment')
    def record_payment(self, request, pk=None):
        """
        Record a payment for an expense.

        Body:
        - amount: Payment amount (required)
        - payment_method: Payment method (optional, default: 'cash')
        - payment_date: Payment date (optional, default: now)
        - notes: Payment notes (optional)
        """
        expense = self.get_object()
        serializer = ExpensePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ExpensePaymentHandler.record_payment(
                expense=expense,
                amount=Decimal(str(serializer.validated_data['amount'])),
                payment_method=serializer.validated_data.get('payment_method', 'cash'),
                payment_date=serializer.validated_data.get('payment_date'),
                notes=serializer.validated_data.get('notes', '')
            )

            # Return updated expense
            response_serializer = ExpenseSerializer(expense)
            return Response(response_serializer.data)

        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)

    @action(detail=False, methods=['get'])
    def unpaid(self, request):
        """
        Get unpaid or partially paid expenses.

        Query params:
        - stall: Stall ID (optional)
        - days_overdue: Filter by days overdue (optional)
        """
        stall_id = request.query_params.get('stall')
        days_overdue = request.query_params.get('days_overdue')

        stall = None
        if stall_id:
            from inventory.models import Stall
            try:
                stall = Stall.objects.get(id=stall_id)
            except Stall.DoesNotExist:
                pass

        days_overdue_int = int(days_overdue) if days_overdue else None

        expenses = ExpensePaymentHandler.get_unpaid_expenses(
            stall=stall,
            days_overdue=days_overdue_int
        )

        # Apply role-based filtering
        expenses = get_role_filtered_queryset(request, expenses)

        serializer = ExpenseListSerializer(expenses, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """Get overdue expenses (unpaid and past 30 days)"""
        expenses = ExpensePaymentHandler.get_unpaid_expenses(days_overdue=30)
        expenses = get_role_filtered_queryset(request, expenses)

        serializer = ExpenseListSerializer(expenses, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='payment-summary')
    def payment_summary(self, request):
        """
        Get payment summary for a period.

        Query params:
        - start_date: Start date (YYYY-MM-DD, required)
        - end_date: End date (YYYY-MM-DD, required)
        - stall: Stall ID (optional)
        """
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not start_date_str or not end_date_str:
            return Response(
                {'error': 'start_date and end_date are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )

        stall_id = request.query_params.get('stall')
        stall = None
        if stall_id:
            from inventory.models import Stall
            try:
                stall = Stall.objects.get(id=stall_id)
            except Stall.DoesNotExist:
                pass

        summary = ExpensePaymentHandler.get_payment_summary(
            start_date=start_date,
            end_date=end_date,
            stall=stall
        )

        return Response(summary)

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        """Mark expense as fully paid"""
        expense = self.get_object()

        if expense.payment_status == Expense.PaymentStatus.PAID:
            return Response(
                {'error': 'Expense is already fully paid'},
                status=status.HTTP_400_BAD_REQUEST
            )

        remaining = expense.balance_due
        try:
            ExpensePaymentHandler.record_payment(
                expense=expense,
                amount=remaining,
                payment_method='cash',
                payment_date=timezone.now()
            )

            serializer = ExpenseSerializer(expense)
            return Response(serializer.data)

        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages)


# ================================
# Expense Analytics ViewSet
# ================================
class ExpenseAnalyticsViewSet(viewsets.ViewSet):
    """
    ViewSet for expense analytics and reporting.

    Provides:
    - Expense summaries
    - Expense trends
    - Category analysis
    - Vendor analysis
    - Period comparisons
    """
    permission_classes = [IsAuthenticated]

    def _parse_date(self, date_str):
        """Parse date string to date object"""
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    def _get_stall_from_request(self, request):
        """Get stall from request parameters"""
        stall_id = request.query_params.get('stall')
        if not stall_id:
            return None

        from inventory.models import Stall
        try:
            return Stall.objects.get(id=stall_id)
        except Stall.DoesNotExist:
            return None

    def _get_category_from_request(self, request):
        """Get category from request parameters"""
        category_id = request.query_params.get('category')
        if not category_id:
            return None

        try:
            return ExpenseCategory.objects.get(id=category_id)
        except ExpenseCategory.DoesNotExist:
            return None

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get expense summary for a period.

        Query params:
        - start_date: Start date (YYYY-MM-DD, required)
        - end_date: End date (YYYY-MM-DD, required)
        - stall: Stall ID (optional)
        - category: Category ID (optional)
        """
        start_date = self._parse_date(request.query_params.get('start_date'))
        end_date = self._parse_date(request.query_params.get('end_date'))

        if not start_date or not end_date:
            # Default to last 30 days
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)

        stall = self._get_stall_from_request(request)
        category = self._get_category_from_request(request)

        summary = ExpenseAnalytics.get_expense_summary(
            start_date=start_date,
            end_date=end_date,
            stall=stall,
            category=category
        )

        return Response(summary)

    @action(detail=False, methods=['get'])
    def trends(self, request):
        """
        Get expense trends over time.

        Query params:
        - start_date: Start date (YYYY-MM-DD, required)
        - end_date: End date (YYYY-MM-DD, required)
        - stall: Stall ID (optional)
        - category: Category ID (optional)
        - interval: 'day', 'week', or 'month' (default: 'month')
        """
        start_date = self._parse_date(request.query_params.get('start_date'))
        end_date = self._parse_date(request.query_params.get('end_date'))

        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=90)

        stall = self._get_stall_from_request(request)
        category = self._get_category_from_request(request)
        interval = request.query_params.get('interval', 'month')

        if interval not in ['day', 'week', 'month']:
            interval = 'month'

        trends = ExpenseAnalytics.get_expense_trends(
            start_date=start_date,
            end_date=end_date,
            stall=stall,
            category=category,
            interval=interval
        )

        return Response(trends)

    @action(detail=False, methods=['get'], url_path='by-category')
    def by_category(self, request):
        """
        Get expenses grouped by category.

        Query params:
        - start_date: Start date (YYYY-MM-DD, optional)
        - end_date: End date (YYYY-MM-DD, optional)
        - stall: Stall ID (optional)
        """
        start_date = self._parse_date(request.query_params.get('start_date'))
        end_date = self._parse_date(request.query_params.get('end_date'))

        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)

        stall = self._get_stall_from_request(request)

        summary = ExpenseAnalytics.get_expense_summary(
            start_date=start_date,
            end_date=end_date,
            stall=stall
        )

        return Response({
            'period': summary['period'],
            'total_expenses': summary['summary']['total_expenses'],
            'categories': summary['category_breakdown']
        })

    @action(detail=False, methods=['get'], url_path='top-vendors')
    def top_vendors(self, request):
        """
        Get top vendors by expense amount.

        Query params:
        - start_date: Start date (YYYY-MM-DD, optional)
        - end_date: End date (YYYY-MM-DD, optional)
        - stall: Stall ID (optional)
        - limit: Number of vendors (default: 10)
        """
        start_date = self._parse_date(request.query_params.get('start_date'))
        end_date = self._parse_date(request.query_params.get('end_date'))

        if not start_date or not end_date:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)

        stall = self._get_stall_from_request(request)
        limit = int(request.query_params.get('limit', 10))

        vendors = ExpenseAnalytics.get_top_vendors(
            start_date=start_date,
            end_date=end_date,
            stall=stall,
            limit=limit
        )

        return Response(vendors)

    @action(detail=False, methods=['get'])
    def comparison(self, request):
        """
        Compare expenses between two periods.

        Query params:
        - current_start: Current period start (YYYY-MM-DD, required)
        - current_end: Current period end (YYYY-MM-DD, required)
        - previous_start: Previous period start (YYYY-MM-DD, required)
        - previous_end: Previous period end (YYYY-MM-DD, required)
        - stall: Stall ID (optional)
        """
        current_start = self._parse_date(request.query_params.get('current_start'))
        current_end = self._parse_date(request.query_params.get('current_end'))
        previous_start = self._parse_date(request.query_params.get('previous_start'))
        previous_end = self._parse_date(request.query_params.get('previous_end'))

        if not all([current_start, current_end, previous_start, previous_end]):
            return Response(
                {'error': 'All date parameters are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        stall = self._get_stall_from_request(request)

        comparison = ExpenseAnalytics.get_expense_comparison(
            current_start=current_start,
            current_end=current_end,
            previous_start=previous_start,
            previous_end=previous_end,
            stall=stall
        )

        return Response(comparison)
