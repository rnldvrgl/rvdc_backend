"""
API serializers for enhanced expense management system.

Handles serialization for:
- Expense categories
- Expenses with payment tracking
- Expense items
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from expenses.models import (
    Expense,
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


class ExpenseCategoryListSerializer(serializers.ModelSerializer):
    """Simplified serializer for category lists"""
    parent_name = serializers.CharField(source='parent.name', read_only=True)

    class Meta:
        model = ExpenseCategory
        fields = ['id', 'name', 'parent', 'parent_name', 'is_active']


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
# Main Expense Serializers
# ================================
class ExpenseSerializer(serializers.ModelSerializer):
    """Comprehensive serializer for expenses"""
    stall_data = serializers.SerializerMethodField()
    category_data = ExpenseCategoryListSerializer(source='category', read_only=True)
    created_by_detail = UserMinimalSerializer(source='created_by', read_only=True)
    items = ExpenseItemSerializer(many=True, read_only=True)

    # Computed fields
    balance_due = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()

    # Display fields
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id',
            'stall',
            'stall_data',
            'category',
            'category_data',
            'expense_date',
            'reference_number',
            'vendor',
            'description',
            'total_price',
            'paid_amount',
            'balance_due',
            'payment_status',
            'payment_status_display',
            'paid_at',
            'payment_method',
            'created_by',
            'created_by_detail',
            'source',
            'items',
            'is_overdue',
            'is_deleted',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'created_by',
            'payment_status',
            'is_deleted',
            'created_at',
            'updated_at',
        ]

    def get_stall_data(self, obj):
        """Return stall data with id and name"""
        if obj.stall:
            return {
                'id': obj.stall.id,
                'name': obj.stall.name,
                'location': obj.stall.location,
            }
        return None

    def get_balance_due(self, obj):
        return float(obj.balance_due)

    def get_is_overdue(self, obj):
        return obj.is_overdue

    def validate(self, attrs):
        # Validate paid_amount doesn't exceed total_price
        total_price = attrs.get('total_price', self.instance.total_price if self.instance else Decimal('0.00'))
        paid_amount = attrs.get('paid_amount', self.instance.paid_amount if self.instance else Decimal('0.00'))

        if paid_amount > total_price:
            raise serializers.ValidationError({
                'paid_amount': 'Paid amount cannot exceed total price'
            })

        return attrs

    def create(self, validated_data):
        # Set created_by from request user
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user

        return super().create(validated_data)


class ExpenseListSerializer(serializers.ModelSerializer):
    """Simplified serializer for expense lists"""
    stall_name = serializers.CharField(source='stall.name', read_only=True)
    stall_data = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    category_data = ExpenseCategoryListSerializer(source='category', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    balance_due = serializers.SerializerMethodField()
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id',
            'stall',
            'stall_name',
            'stall_data',
            'category',
            'category_name',
            'category_data',
            'expense_date',
            'vendor',
            'description',
            'total_price',
            'paid_amount',
            'balance_due',
            'payment_status',
            'payment_status_display',
            'payment_method',
            'created_by_name',
            'source',
            'is_deleted',
            'created_at',
        ]

    def get_stall_data(self, obj):
        """Return stall data with id and name"""
        if obj.stall:
            return {
                'id': obj.stall.id,
                'name': obj.stall.name,
                'location': obj.stall.location,
            }
        return None

    def get_balance_due(self, obj):
        return float(obj.balance_due)


# ================================
# Payment Serializers
# ================================
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
