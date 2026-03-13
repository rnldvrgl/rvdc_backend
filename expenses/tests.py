"""
Comprehensive test suite for expense management system.

Tests:
- Expense category CRUD and hierarchy
- Expense creation and validation
- Payment recording and tracking
- Business logic operations
- Analytics and reporting
- API endpoints
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from inventory.models import Item, Stall
from rest_framework import status
from rest_framework.test import APITestCase

from expenses.business_logic import (
    ExpenseAnalytics,
    ExpenseCategoryManager,
    ExpenseManager,
    ExpensePaymentHandler,
)
from expenses.models import Expense, ExpenseCategory, ExpenseItem

User = get_user_model()


# ================================
# Model Tests
# ================================
class ExpenseCategoryModelTest(TestCase):
    """Test ExpenseCategory model"""

    def setUp(self):
        self.main_stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True
        )

    def test_create_category(self):
        """Test creating a basic category"""
        category = ExpenseCategory.objects.create(
            name="Utilities",
            description="Power and water bills",
            monthly_budget=Decimal('5000.00')
        )

        self.assertEqual(category.name, "Utilities")
        self.assertEqual(category.monthly_budget, Decimal('5000.00'))
        self.assertTrue(category.is_active)
        self.assertFalse(category.is_deleted)

    def test_hierarchical_categories(self):
        """Test parent-child category relationships"""
        parent = ExpenseCategory.objects.create(
            name="Utilities",
            monthly_budget=Decimal('10000.00')
        )

        child = ExpenseCategory.objects.create(
            name="Electricity",
            parent=parent,
            monthly_budget=Decimal('6000.00')
        )

        self.assertEqual(child.parent, parent)
        self.assertEqual(parent.subcategories.count(), 1)
        self.assertEqual(child.get_full_path(), "Utilities > Electricity")

    def test_get_total_budget(self):
        """Test total budget calculation including subcategories"""
        parent = ExpenseCategory.objects.create(
            name="Utilities",
            monthly_budget=Decimal('2000.00')
        )

        ExpenseCategory.objects.create(
            name="Electricity",
            parent=parent,
            monthly_budget=Decimal('5000.00')
        )

        ExpenseCategory.objects.create(
            name="Water",
            parent=parent,
            monthly_budget=Decimal('2000.00')
        )

        # Total = 2000 + 5000 + 2000 = 9000
        self.assertEqual(parent.get_total_budget(), Decimal('9000.00'))

    def test_soft_delete_category(self):
        """Test soft delete functionality"""
        category = ExpenseCategory.objects.create(name="Test Category")

        category.soft_delete()

        self.assertTrue(category.is_deleted)
        self.assertFalse(category.is_active)


class ExpenseModelTest(TestCase):
    """Test Expense model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role='admin'
        )

        self.stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True
        )

        self.category = ExpenseCategory.objects.create(
            name="Utilities",
            monthly_budget=Decimal('5000.00')
        )

    def test_create_expense(self):
        """Test creating an expense"""
        expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            expense_date=timezone.now().date(),
            total_price=Decimal('1500.00'),
            description="Electricity bill",
            vendor="Power Company",
            reference_number="INV-001",
            created_by=self.user
        )

        self.assertEqual(expense.total_price, Decimal('1500.00'))
        self.assertEqual(expense.payment_status, Expense.PaymentStatus.UNPAID)
        self.assertEqual(expense.paid_amount, Decimal('0.00'))
        self.assertEqual(expense.balance_due, Decimal('1500.00'))

    def test_payment_status_updates(self):
        """Test automatic payment status updates"""
        expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        # Initially unpaid
        self.assertEqual(expense.payment_status, Expense.PaymentStatus.UNPAID)

        # Partial payment
        expense.paid_amount = Decimal('500.00')
        expense.save()
        self.assertEqual(expense.payment_status, Expense.PaymentStatus.PARTIAL)

        # Full payment
        expense.paid_amount = Decimal('1000.00')
        expense.save()
        self.assertEqual(expense.payment_status, Expense.PaymentStatus.PAID)
        self.assertIsNotNone(expense.paid_at)

    def test_is_overdue_property(self):
        """Test overdue calculation"""
        # Recent expense - not overdue
        recent_expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            expense_date=timezone.now().date() - timedelta(days=10),
            total_price=Decimal('1000.00'),
            created_by=self.user
        )
        self.assertFalse(recent_expense.is_overdue)

        # Old unpaid expense - overdue
        old_expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            expense_date=timezone.now().date() - timedelta(days=35),
            total_price=Decimal('1000.00'),
            created_by=self.user
        )
        self.assertTrue(old_expense.is_overdue)

        # Old but paid expense - not overdue
        old_expense.paid_amount = Decimal('1000.00')
        old_expense.save()
        self.assertFalse(old_expense.is_overdue)

    def test_record_payment(self):
        """Test recording payments"""
        expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        # Record partial payment
        expense.record_payment(
            amount=Decimal('500.00'),
            payment_method='cash'
        )

        self.assertEqual(expense.paid_amount, Decimal('500.00'))
        self.assertEqual(expense.payment_status, Expense.PaymentStatus.PARTIAL)
        self.assertEqual(expense.balance_due, Decimal('500.00'))

        # Record remaining payment
        expense.record_payment(
            amount=Decimal('500.00'),
            payment_method='bank_transfer'
        )

        self.assertEqual(expense.paid_amount, Decimal('1000.00'))
        self.assertEqual(expense.payment_status, Expense.PaymentStatus.PAID)
        self.assertEqual(expense.balance_due, Decimal('0.00'))

    def test_overpayment_prevention(self):
        """Test that overpayments are prevented"""
        expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            expense.record_payment(amount=Decimal('1500.00'))

    def test_recurring_expense_validation(self):
        """Test recurring expense validation"""
        from django.core.exceptions import ValidationError

        # Recurring without frequency should fail
        expense = Expense(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            recurring=True,
            created_by=self.user
        )

        with self.assertRaises(ValidationError):
            expense.full_clean()


class ExpenseItemModelTest(TestCase):
    """Test ExpenseItem model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role='admin'
        )

        self.stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True
        )

        self.category = ExpenseCategory.objects.create(name="Supplies")

        self.expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('5000.00'),
            created_by=self.user
        )

        self.item = Item.objects.create(
            name="Test Item",
            retail_price=Decimal('100.00'),
            unit_of_measure='pcs'
        )

    def test_create_expense_item(self):
        """Test creating expense item"""
        expense_item = ExpenseItem.objects.create(
            expense=self.expense,
            item=self.item,
            description="Test item purchase",
            quantity=10,
            unit_price=Decimal('100.00'),
            total_price=Decimal('1000.00')
        )

        self.assertEqual(expense_item.quantity, 10)
        self.assertEqual(expense_item.total_price, Decimal('1000.00'))

    def test_auto_calculate_total_price(self):
        """Test automatic total price calculation"""
        expense_item = ExpenseItem.objects.create(
            expense=self.expense,
            item=self.item,
            description="Test item",
            quantity=5,
            unit_price=Decimal('200.00')
        )

        self.assertEqual(expense_item.total_price, Decimal('1000.00'))

    def test_auto_set_description_from_item(self):
        """Test auto-setting description from item"""
        expense_item = ExpenseItem.objects.create(
            expense=self.expense,
            item=self.item,
            quantity=1,
            unit_price=Decimal('100.00')
        )

        self.assertEqual(expense_item.description, "Test Item")


# ================================
# Business Logic Tests
# ================================
class ExpenseManagerTest(TestCase):
    """Test ExpenseManager business logic"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='manager',
            password='testpass123',
            role='manager'
        )

        self.stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True
        )

        self.category = ExpenseCategory.objects.create(
            name="Utilities",
            monthly_budget=Decimal('5000.00')
        )

    def test_create_expense(self):
        """Test creating expense via manager"""
        expense = ExpenseManager.create_expense(
            stall=self.stall,
            category=self.category,
            expense_date=timezone.now().date(),
            total_price=Decimal('1500.00'),
            description="Test expense",
            vendor="Test Vendor",
            reference_number="REF-001",
            created_by=self.user
        )

        self.assertIsNotNone(expense.id)
        self.assertEqual(expense.total_price, Decimal('1500.00'))
        self.assertEqual(expense.created_by, self.user)

    def test_create_expense_with_items(self):
        """Test creating expense with line items"""
        items = [
            {
                'description': 'Item 1',
                'quantity': 2,
                'unit_price': Decimal('100.00')
            },
            {
                'description': 'Item 2',
                'quantity': 1,
                'unit_price': Decimal('300.00')
            }
        ]

        expense = ExpenseManager.create_expense(
            stall=self.stall,
            category=self.category,
            expense_date=timezone.now().date(),
            total_price=Decimal('500.00'),
            created_by=self.user,
            items=items
        )

        self.assertEqual(expense.items.count(), 2)

    def test_update_expense(self):
        """Test updating expense"""
        expense = ExpenseManager.create_expense(
            stall=self.stall,
            category=self.category,
            expense_date=timezone.now().date(),
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        updated = ExpenseManager.update_expense(
            expense,
            description="Updated description",
            vendor="New Vendor"
        )

        self.assertEqual(updated.description, "Updated description")
        self.assertEqual(updated.vendor, "New Vendor")

    def test_cannot_update_paid_expense(self):
        """Test that paid expenses cannot be updated"""
        from django.core.exceptions import ValidationError

        expense = ExpenseManager.create_expense(
            stall=self.stall,
            category=self.category,
            expense_date=timezone.now().date(),
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        expense.paid_amount = Decimal('1000.00')
        expense.save()

        with self.assertRaises(ValidationError):
            ExpenseManager.update_expense(expense, description="New description")

    def test_delete_expense(self):
        """Test soft deleting expense"""
        expense = ExpenseManager.create_expense(
            stall=self.stall,
            category=self.category,
            expense_date=timezone.now().date(),
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        ExpenseManager.delete_expense(expense)

        self.assertTrue(expense.is_deleted)
        self.assertIsNotNone(expense.deleted_at)

    def test_get_expense_summary(self):
        """Test expense summary generation"""
        expense = ExpenseManager.create_expense(
            stall=self.stall,
            category=self.category,
            expense_date=timezone.now().date(),
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        summary = ExpenseManager.get_expense_summary(expense)

        self.assertEqual(summary['id'], expense.id)
        self.assertEqual(summary['total_price'], 1000.00)
        self.assertEqual(summary['balance_due'], 1000.00)
        self.assertEqual(summary['payment_status'], 'unpaid')


class ExpensePaymentHandlerTest(TestCase):
    """Test ExpensePaymentHandler business logic"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role='admin'
        )

        self.stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True
        )

        self.category = ExpenseCategory.objects.create(name="Utilities")

    def test_record_payment(self):
        """Test recording payment"""
        expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        ExpensePaymentHandler.record_payment(
            expense=expense,
            amount=Decimal('500.00'),
            payment_method='cash'
        )

        expense.refresh_from_db()
        self.assertEqual(expense.paid_amount, Decimal('500.00'))
        self.assertEqual(expense.payment_status, Expense.PaymentStatus.PARTIAL)

    def test_prevent_overpayment(self):
        """Test overpayment prevention"""
        from django.core.exceptions import ValidationError

        expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        with self.assertRaises(ValidationError):
            ExpensePaymentHandler.record_payment(
                expense=expense,
                amount=Decimal('1500.00')
            )

    def test_get_unpaid_expenses(self):
        """Test retrieving unpaid expenses"""
        # Create paid expense
        paid_expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            paid_amount=Decimal('1000.00'),
            created_by=self.user
        )

        # Create unpaid expense
        unpaid_expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('2000.00'),
            created_by=self.user
        )

        unpaid = ExpensePaymentHandler.get_unpaid_expenses()

        self.assertEqual(unpaid.count(), 1)
        self.assertEqual(unpaid.first().id, unpaid_expense.id)

    def test_get_overdue_expenses(self):
        """Test retrieving overdue expenses"""
        # Create old unpaid expense (overdue)
        old_date = timezone.now().date() - timedelta(days=40)
        overdue_expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            expense_date=old_date,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        # Create recent unpaid expense (not overdue)
        recent_expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            expense_date=timezone.now().date(),
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        overdue = ExpensePaymentHandler.get_unpaid_expenses(days_overdue=30)

        self.assertEqual(overdue.count(), 1)
        self.assertEqual(overdue.first().id, overdue_expense.id)

    def test_payment_summary(self):
        """Test payment summary generation"""
        start_date = timezone.now().date() - timedelta(days=7)
        end_date = timezone.now().date()

        # Create test expenses
        Expense.objects.create(
            stall=self.stall,
            category=self.category,
            expense_date=start_date + timedelta(days=1),
            total_price=Decimal('1000.00'),
            paid_amount=Decimal('1000.00'),
            created_by=self.user
        )

        Expense.objects.create(
            stall=self.stall,
            category=self.category,
            expense_date=start_date + timedelta(days=2),
            total_price=Decimal('2000.00'),
            paid_amount=Decimal('500.00'),
            created_by=self.user
        )

        summary = ExpensePaymentHandler.get_payment_summary(
            start_date=start_date,
            end_date=end_date,
            stall=self.stall
        )

        self.assertEqual(summary['total_expenses'], 3000.00)
        self.assertEqual(summary['total_paid'], 1500.00)
        self.assertEqual(summary['balance_due'], 1500.00)
        self.assertEqual(summary['expense_count'], 2)


class ExpenseCategoryManagerTest(TestCase):
    """Test ExpenseCategoryManager business logic"""

    def test_create_category(self):
        """Test creating category via manager"""
        category = ExpenseCategoryManager.create_category(
            name="Utilities",
            description="Power and water",
            monthly_budget=Decimal('5000.00')
        )

        self.assertEqual(category.name, "Utilities")
        self.assertEqual(category.monthly_budget, Decimal('5000.00'))

    def test_duplicate_category_prevention(self):
        """Test duplicate category name prevention"""
        from django.core.exceptions import ValidationError

        ExpenseCategoryManager.create_category(name="Utilities")

        with self.assertRaises(ValidationError):
            ExpenseCategoryManager.create_category(name="Utilities")

    def test_get_categories_with_stats(self):
        """Test getting categories with statistics"""
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role='admin'
        )

        stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True
        )

        category = ExpenseCategoryManager.create_category(
            name="Utilities",
            monthly_budget=Decimal('5000.00')
        )

        # Create some expenses in this category
        Expense.objects.create(
            stall=stall,
            category=category,
            total_price=Decimal('1500.00'),
            created_by=user
        )

        Expense.objects.create(
            stall=stall,
            category=category,
            total_price=Decimal('2000.00'),
            created_by=user
        )

        stats = ExpenseCategoryManager.get_categories_with_stats()

        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]['name'], "Utilities")
        self.assertEqual(stats[0]['total_expenses'], 3500.00)
        self.assertEqual(stats[0]['expense_count'], 2)


class ExpenseAnalyticsTest(TestCase):
    """Test ExpenseAnalytics business logic"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role='admin'
        )

        self.stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True
        )

        self.utilities = ExpenseCategory.objects.create(name="Utilities")
        self.supplies = ExpenseCategory.objects.create(name="Supplies")

    def test_expense_summary(self):
        """Test expense summary analytics"""
        start_date = timezone.now().date() - timedelta(days=7)
        end_date = timezone.now().date()

        # Create test expenses
        Expense.objects.create(
            stall=self.stall,
            category=self.utilities,
            expense_date=start_date + timedelta(days=1),
            total_price=Decimal('1000.00'),
            paid_amount=Decimal('1000.00'),
            created_by=self.user
        )

        Expense.objects.create(
            stall=self.stall,
            category=self.supplies,
            expense_date=start_date + timedelta(days=2),
            total_price=Decimal('2000.00'),
            created_by=self.user
        )

        summary = ExpenseAnalytics.get_expense_summary(
            start_date=start_date,
            end_date=end_date,
            stall=self.stall
        )

        self.assertEqual(summary['summary']['total_expenses'], 3000.00)
        self.assertEqual(summary['summary']['total_paid'], 1000.00)
        self.assertEqual(summary['summary']['expense_count'], 2)
        self.assertEqual(len(summary['category_breakdown']), 2)

    def test_expense_trends(self):
        """Test expense trends over time"""
        start_date = timezone.now().date() - timedelta(days=30)
        end_date = timezone.now().date()

        # Create expenses over time
        for i in range(5):
            Expense.objects.create(
                stall=self.stall,
                category=self.utilities,
                expense_date=start_date + timedelta(days=i * 5),
                total_price=Decimal('1000.00'),
                created_by=self.user
            )

        trends = ExpenseAnalytics.get_expense_trends(
            start_date=start_date,
            end_date=end_date,
            stall=self.stall,
            interval='week'
        )

        self.assertGreater(len(trends), 0)

    def test_top_vendors(self):
        """Test top vendors analytics"""
        start_date = timezone.now().date() - timedelta(days=30)
        end_date = timezone.now().date()

        # Create expenses with different vendors
        Expense.objects.create(
            stall=self.stall,
            category=self.utilities,
            expense_date=start_date,
            vendor="Vendor A",
            total_price=Decimal('5000.00'),
            created_by=self.user
        )

        Expense.objects.create(
            stall=self.stall,
            category=self.supplies,
            expense_date=start_date,
            vendor="Vendor B",
            total_price=Decimal('3000.00'),
            created_by=self.user
        )

        Expense.objects.create(
            stall=self.stall,
            category=self.utilities,
            expense_date=start_date,
            vendor="Vendor A",
            total_price=Decimal('2000.00'),
            created_by=self.user
        )

        vendors = ExpenseAnalytics.get_top_vendors(
            start_date=start_date,
            end_date=end_date,
            limit=5
        )

        self.assertEqual(len(vendors), 2)
        self.assertEqual(vendors[0]['vendor'], "Vendor A")
        self.assertEqual(vendors[0]['total_expenses'], 7000.00)

    def test_expense_comparison(self):
        """Test expense period comparison"""
        # Current period
        current_start = timezone.now().date() - timedelta(days=7)
        current_end = timezone.now().date()

        # Previous period
        previous_start = current_start - timedelta(days=7)
        previous_end = current_start - timedelta(days=1)

        # Create expenses in both periods
        Expense.objects.create(
            stall=self.stall,
            category=self.utilities,
            expense_date=previous_start,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        Expense.objects.create(
            stall=self.stall,
            category=self.utilities,
            expense_date=current_start,
            total_price=Decimal('1500.00'),
            created_by=self.user
        )

        comparison = ExpenseAnalytics.get_expense_comparison(
            current_start=current_start,
            current_end=current_end,
            previous_start=previous_start,
            previous_end=previous_end,
            stall=self.stall
        )

        self.assertEqual(comparison['current_period']['total_expenses'], 1500.00)
        self.assertEqual(comparison['previous_period']['total_expenses'], 1000.00)
        self.assertEqual(comparison['comparison']['change'], 500.00)
        self.assertEqual(comparison['comparison']['trend'], 'up')


# ================================
# API Tests
# ================================
class ExpenseCategoryAPITest(APITestCase):
    """Test ExpenseCategory API endpoints"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role='admin'
        )
        self.client.force_authenticate(user=self.user)

    def test_list_categories(self):
        """Test listing expense categories"""
        ExpenseCategory.objects.create(name="Utilities")
        ExpenseCategory.objects.create(name="Supplies")

        response = self.client.get('/api/expenses/categories/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_create_category(self):
        """Test creating expense category"""
        data = {
            'name': 'Marketing',
            'description': 'Marketing and advertising',
            'monthly_budget': '5000.00'
        }

        response = self.client.post('/api/expenses/categories/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Marketing')

    def test_create_subcategory(self):
        """Test creating subcategory"""
        parent = ExpenseCategory.objects.create(name="Utilities")

        data = {
            'name': 'Electricity',
            'parent': parent.id,
            'monthly_budget': '3000.00'
        }

        response = self.client.post('/api/expenses/categories/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['parent'], parent.id)

    def test_get_categories_with_stats(self):
        """Test getting categories with statistics"""
        category = ExpenseCategory.objects.create(name="Utilities")
        stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True
        )

        Expense.objects.create(
            stall=stall,
            category=category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        response = self.client.get('/api/expenses/categories/with_stats/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data), 0)


class ExpenseAPITest(APITestCase):
    """Test Expense API endpoints"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role='admin'
        )
        self.client.force_authenticate(user=self.user)

        self.stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True
        )

        self.category = ExpenseCategory.objects.create(name="Utilities")

    def test_list_expenses(self):
        """Test listing expenses"""
        Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        response = self.client.get('/api/expenses/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data['results']), 0)

    def test_create_expense(self):
        """Test creating expense"""
        data = {
            'stall': self.stall.id,
            'category': self.category.id,
            'expense_date': timezone.now().date().isoformat(),
            'total_price': '1500.00',
            'description': 'Test expense',
            'vendor': 'Test Vendor',
            'reference_number': 'REF-001'
        }

        response = self.client.post('/api/expenses/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['total_price'], '1500.00')
        self.assertEqual(response.data['created_by'], self.user.id)

    def test_record_payment(self):
        """Test recording payment via API"""
        expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        data = {
            'amount': '500.00',
            'payment_method': 'cash'
        }

        response = self.client.post(
            f'/api/expenses/{expense.id}/record-payment/',
            data
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['paid_amount'], '500.00')

    def test_mark_as_paid(self):
        """Test marking expense as fully paid"""
        expense = Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        response = self.client.post(f'/api/expenses/{expense.id}/mark-paid/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['payment_status'], 'paid')

    def test_get_unpaid_expenses(self):
        """Test getting unpaid expenses"""
        # Create paid expense
        Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            paid_amount=Decimal('1000.00'),
            created_by=self.user
        )

        # Create unpaid expense
        Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('2000.00'),
            created_by=self.user
        )

        response = self.client.get('/api/expenses/unpaid/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_filter_by_category(self):
        """Test filtering expenses by category"""
        other_category = ExpenseCategory.objects.create(name="Supplies")

        Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        Expense.objects.create(
            stall=self.stall,
            category=other_category,
            total_price=Decimal('2000.00'),
            created_by=self.user
        )

        response = self.client.get(
            f'/api/expenses/?category={self.category.id}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_filter_by_payment_status(self):
        """Test filtering by payment status"""
        Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        Expense.objects.create(
            stall=self.stall,
            category=self.category,
            total_price=Decimal('2000.00'),
            paid_amount=Decimal('2000.00'),
            created_by=self.user
        )

        response = self.client.get('/api/expenses/?payment_status=unpaid')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)


class ExpenseAnalyticsAPITest(APITestCase):
    """Test Expense Analytics API endpoints"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role='admin'
        )
        self.client.force_authenticate(user=self.user)

        self.stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True
        )

        self.category = ExpenseCategory.objects.create(name="Utilities")

    def test_expense_summary_endpoint(self):
        """Test expense summary analytics endpoint"""
        start_date = timezone.now().date() - timedelta(days=7)
        end_date = timezone.now().date()

        Expense.objects.create(
            stall=self.stall,
            category=self.category,
            expense_date=start_date + timedelta(days=1),
            total_price=Decimal('1000.00'),
            created_by=self.user
        )

        response = self.client.get(
            f'/api/expenses/analytics/summary/'
            f'?start_date={start_date}&end_date={end_date}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('summary', response.data)
        self.assertIn('category_breakdown', response.data)

    def test_expense_trends_endpoint(self):
        """Test expense trends endpoint"""
        start_date = timezone.now().date() - timedelta(days=30)
        end_date = timezone.now().date()

        response = self.client.get(
            f'/api/expenses/analytics/trends/'
            f'?start_date={start_date}&end_date={end_date}&interval=week'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_top_vendors_endpoint(self):
        """Test top vendors endpoint"""
        start_date = timezone.now().date() - timedelta(days=30)
        end_date = timezone.now().date()

        Expense.objects.create(
            stall=self.stall,
            category=self.category,
            expense_date=start_date,
            vendor="Vendor A",
            total_price=Decimal('5000.00'),
            created_by=self.user
        )

        response = self.client.get(
            f'/api/expenses/analytics/top-vendors/'
            f'?start_date={start_date}&end_date={end_date}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data), 0)

    def test_expense_comparison_endpoint(self):
        """Test expense comparison endpoint"""
        current_start = timezone.now().date() - timedelta(days=7)
        current_end = timezone.now().date()
        previous_start = current_start - timedelta(days=7)
        previous_end = current_start - timedelta(days=1)

        response = self.client.get(
            f'/api/expenses/analytics/comparison/'
            f'?current_start={current_start}&current_end={current_end}'
            f'&previous_start={previous_start}&previous_end={previous_end}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('current_period', response.data)
        self.assertIn('previous_period', response.data)
        self.assertIn('comparison', response.data)
