from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AnalyticsViewSet,
    CalendarEventsView,
    CalendarEventViewSet,
    CashFlowView,
    ExpensesOverTimeView,
    SalesOverTimeView,
    SummaryStatsView,
    TopClientsView,
    TopSellingItemsView,
    UnpaidSalesStatusView,
)

# Router for viewset-based analytics endpoints
router = DefaultRouter()
router.register(r'reports', AnalyticsViewSet, basename='analytics')
router.register(r'calendar-events', CalendarEventViewSet, basename='calendar-event')

# Legacy and additional URL patterns
urlpatterns = [
    # Legacy endpoints (kept for backward compatibility)
    path("summary/", SummaryStatsView.as_view(), name="summary-stats"),
    path(
        "charts/sales-over-time/", SalesOverTimeView.as_view(), name="sales-over-time"
    ),
    path(
        "charts/expenses-over-time/",
        ExpensesOverTimeView.as_view(),
        name="expenses-over-time",
    ),
    path(
        "charts/top-selling-items/",
        TopSellingItemsView.as_view(),
        name="top-selling-items",
    ),
    path("charts/cash-flow/", CashFlowView.as_view(), name="cash-flow"),
    path("charts/top-clients/", TopClientsView.as_view(), name="top-clients"),
    path(
        "charts/unpaid-sales-status/",
        UnpaidSalesStatusView.as_view(),
        name="unpaid-sales-status",
    ),
    path("calendar/events/", CalendarEventsView.as_view(), name="calendar-events"),
]

# Include router URLs
urlpatterns += router.urls
