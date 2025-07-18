from django.urls import path
from .views import (
    SalesOverTimeView,
    ExpensesOverTimeView,
    TopSellingItemsView,
    CashFlowView,
    TopClientsView,
    UnpaidSalesStatusView,
    RestocksOverTimeView,
    SummaryStatsView,
)

urlpatterns = [
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
    path(
        "charts/restocks-over-time/",
        RestocksOverTimeView.as_view(),
        name="restocks-over-time",
    ),
]
