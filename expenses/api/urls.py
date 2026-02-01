"""
URL routing for expense management API.

Provides routes for:
- Expense categories (CRUD, stats)
- Expenses (CRUD, payments, filtering) - Stall expenses
- Expense analytics (summaries, trends, reports)
"""

from rest_framework.routers import DefaultRouter

from .views import (
    ExpenseAnalyticsViewSet,
    ExpenseCategoryViewSet,
    ExpenseViewSet,
)

# Create router
router = DefaultRouter()

# Register ViewSets
router.register(r'categories', ExpenseCategoryViewSet, basename='expense-category')
router.register(r'analytics', ExpenseAnalyticsViewSet, basename='expense-analytics')
router.register(r'', ExpenseViewSet, basename='expense')

# URL patterns
urlpatterns = router.urls
