"""
API serializers for enhanced expense management system.

Handles serialization for:
- Expense categories
- Expense budgets
- Expenses with approval workflow
- Expense items
- Expense attachments
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from expenses.models import (
    Expense,
    ExpenseAttachment,
    ExpenseBudget,
    ExpenseCategory,
    ExpenseItem,
)
from rest_framework import serializers

User = get_user_model()


# ================================
# User Serializers (nested)
# ================================
class UserMinimalSerializer(serializers.ModelSerializer):
    """Minimal user info for nested serialization"""
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'full_name']
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name() if hasattr(obj, 'get_full_name') else f"{obj.first_name} {obj.last_name}".strip()


# ================================
# Expense Category Serializers
# ================================
class ExpenseCategorySerializer(serializers.ModelSerializer):
    """Serializer for expense categories"""
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    full_path = serializers.SerializerMethodField()
    subcategories_count = serializers.SerializerMethodField()
    total_budget = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseCategory
        fields = [
            'id',
            'name',
            'description',
            'monthly_budget',
            'parent',
            'parent_name',
            'full_path',
            'is_active',
            'subcategories_count',
            'total_budget',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_full_path(self, obj):
        return obj.get_full_path()

    def get_subcategories_count(self, obj):
        return obj.subcategories.filter(is_deleted=False).count()

    def get_total_budget(self, obj):
        return float(obj.get_total_budget())

    def validate(self, attrs):
        # Prevent circular parent references
        if 'parent' in attrs and attrs['parent']:
            parent = attrs['parent']
            if self.instance and parent.id == self.instance.id:
                raise serializers.ValidationError({
                    'parent': 'Category cannot be its own parent'
                })
            # Check if parent is a descendant
            if self.instance and self._is_descendant(self.instance, parent):
                raise serializers.ValidationError({
                    'parent': 'Cannot set a descendant as parent (circular reference)'
                })
        return attrs

    def _is_descendant(self, category, potential_parent):
        """Check if potential_parent is a descendant of category"""
        current = potential_parent
        while current.parent:
            if current.parent.id == category.id:
                return True
            current = current.parent
        return False


class ExpenseCategoryListSerializer(serializers.ModelSerializer):
    """Simplified serializer for category lists"""
    parent_name = serializers.CharField(source='parent.name', read_only=True)

    class Meta:
        model = ExpenseCategory
        fields = ['id', 'name', 'parent', 'parent_name', 'is_active']


# ================================
# Expense Budget Serializers
# ================================
class ExpenseBudgetSerializer(serializers.ModelSerializer):
    """Serializer for expense budgets"""
    stall_name = serializers.CharField(source='stall.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    actual_expenses = serializers.SerializerMethodField()
    variance = serializers.SerializerMethodField()
    utilization_percentage = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseBudget
        fields = [
            'id',
            'stall',
            'stall_name',
            'category',
            'category_name',
            'month',
            'year',
            'budgeted_amount',
            'actual_expenses',
            'variance',
            'utilization_percentage',
            'status',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_actual_expenses(self, obj):
        return float(obj.actual_expenses)

    def get_variance(self, obj):
        return float(obj.variance)

    def get_utilization_percentage(self, obj):
        return float(obj.utilization_percentage)

    def get_status(self, obj):
        if obj.variance < 0:
            return 'over_budget'
        elif obj.utilization_percentage >= 90:
            return 'approaching_limit'
        else:
            return 'within_budget'

    def validate(self, attrs):
        month = attrs.get('month')
        year = attrs.get('year')

        if month and (month < 1 or month > 12):
            raise serializers.ValidationError({'month': 'Month must be between 1 and 12'})

        if year and year < 2000:
            raise serializers.ValidationError({'year': 'Year must be 2000 or later'})

        return attrs


# ================================
# Expense Item Serializers
# ================================
class ExpenseItemSerializer(serializers.ModelSerializer):
    """Serializer for expense line items"""
    item_name = serializers.CharField(source='item.name', read_only=True)

    class Meta:
        model = ExpenseItem
        fields = [
            'id',
            'item',
            'item_name',
            'description',
            'quantity',
            'unit_price',
            'total_price',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        # Check if expense has been paid
        expense = self.context.get('expense')
        if expense and expense.paid_amount > 0:
            raise serializers.ValidationError("Cannot edit items after payment has been made")

        # Validate total_price calculation
        if 'quantity' in attrs and 'unit_price' in attrs:
            calculated_total = attrs['quantity'] * attrs['unit_price']
            if 'total_price' in attrs and attrs['total_price'] != calculated_total:
                raise serializers.ValidationError({
                    'total_price': 'Total price must equal quantity × unit price'
                })

        return attrs


# ================================
# Expense Attachment Serializers
# ================================
class ExpenseAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for expense attachments"""
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseAttachment
        fields = [
            'id',
            'file',
            'file_url',
            'filename',
            'file_type',
            'file_size',
            'description',
            'uploaded_by',
            'uploaded_by_name',
            'uploaded_at',
        ]
        read_only_fields = ['filename', 'file_type', 'file_size', 'uploaded_by', 'uploaded_at']

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None


# ================================
# Main Expense Serializers
# ================================
class ExpenseSerializer(serializers.ModelSerializer):
    """Comprehensive serializer for expenses"""
    stall_name = serializers.CharField(source='stall.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    submitted_by_detail = UserMinimalSerializer(source='submitted_by', read_only=True)
    approved_by_detail = UserMinimalSerializer(source='approved_by', read_only=True)
    items = ExpenseItemSerializer(many=True, read_only=True)
    attachments = ExpenseAttachmentSerializer(many=True, read_only=True)

    # Computed fields
    balance_due = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    is_pending_approval = serializers.SerializerMethodField()
    is_approved = serializers.SerializerMethodField()

    # Display fields
    approval_status_display = serializers.CharField(source='get_approval_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id',
            'stall',
            'stall_name',
            'category',
            'category_name',
            'expense_date',
            'reference_number',
            'vendor',
            'description',
            'total_price',
            'paid_amount',
            'balance_due',
            'approval_status',
            'approval_status_display',
            'payment_status',
            'payment_status_display',
            'priority',
            'priority_display',
            'paid_at',
            'payment_method',
            'submitted_by',
            'submitted_by_detail',
            'approved_by',
            'approved_by_detail',
            'approved_at',
            'rejection_reason',
            'source',
            'recurring',
            'recurring_frequency',
            'items',
            'attachments',
            'is_overdue',
            'is_pending_approval',
            'is_approved',
            'is_deleted',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'submitted_by',
            'approved_by',
            'approved_at',
            'payment_status',
            'is_deleted',
            'created_at',
            'updated_at',
        ]

    def get_balance_due(self, obj):
        return float(obj.balance_due)

    def get_is_overdue(self, obj):
        return obj.is_overdue

    def get_is_pending_approval(self, obj):
        return obj.is_pending_approval

    def get_is_approved(self, obj):
        return obj.is_approved

    def validate(self, attrs):
        # Validate paid_amount doesn't exceed total_price
        total_price = attrs.get('total_price', self.instance.total_price if self.instance else Decimal('0.00'))
        paid_amount = attrs.get('paid_amount', self.instance.paid_amount if self.instance else Decimal('0.00'))

        if paid_amount > total_price:
            raise serializers.ValidationError({
                'paid_amount': 'Paid amount cannot exceed total price'
            })

        # Validate recurring frequency
        recurring = attrs.get('recurring', self.instance.recurring if self.instance else False)
        recurring_frequency = attrs.get('recurring_frequency', self.instance.recurring_frequency if self.instance else None)

        if recurring and not recurring_frequency:
            raise serializers.ValidationError({
                'recurring_frequency': 'Frequency is required for recurring expenses'
            })

        return attrs

    def create(self, validated_data):
        # Set submitted_by from request user
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['submitted_by'] = request.user
            validated_data['created_by'] = request.user

        return super().create(validated_data)


class ExpenseListSerializer(serializers.ModelSerializer):
    """Simplified serializer for expense lists"""
    stall_name = serializers.CharField(source='stall.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    submitted_by_name = serializers.CharField(source='submitted_by.get_full_name', read_only=True)
    balance_due = serializers.SerializerMethodField()
    approval_status_display = serializers.CharField(source='get_approval_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id',
            'stall',
            'stall_name',
            'category',
            'category_name',
            'expense_date',
            'reference_number',
            'vendor',
            'description',
            'total_price',
            'paid_amount',
            'balance_due',
            'approval_status',
            'approval_status_display',
            'payment_status',
            'payment_status_display',
            'priority',
            'submitted_by_name',
            'created_at',
        ]

    def get_balance_due(self, obj):
        return float(obj.balance_due)


# ================================
# Action Serializers
# ================================
class ExpenseApprovalSerializer(serializers.Serializer):
    """Serializer for approving expenses"""
    notes = serializers.CharField(required=False, allow_blank=True)


class ExpenseRejectionSerializer(serializers.Serializer):
    """Serializer for rejecting expenses"""
    reason = serializers.CharField(required=True)

    def validate_reason(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Rejection reason cannot be empty")
        return value


class ExpensePaymentSerializer(serializers.Serializer):
    """Serializer for recording expense payments"""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    payment_method = serializers.CharField(required=False, default='cash')
    payment_date = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be positive")
        return value


class BulkApprovalSerializer(serializers.Serializer):
    """Serializer for bulk expense approval"""
    expense_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False
    )
    notes = serializers.CharField(required=False, allow_blank=True)


# ================================
# Summary/Report Serializers
# ================================
class ExpenseSummarySerializer(serializers.Serializer):
    """Serializer for expense summary data"""
    period = serializers.DictField()
    summary = serializers.DictField()
    category_breakdown = serializers.ListField()
    approval_breakdown = serializers.ListField()
    payment_breakdown = serializers.ListField()
