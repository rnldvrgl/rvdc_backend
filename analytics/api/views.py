from datetime import datetime, time, timedelta

from analytics.business_logic import (
    ClientAnalytics,
    DashboardAnalytics,
    InventoryAnalytics,
    OutstandingAnalytics,
    PaymentAnalytics,
    RevenueAnalytics,
    ServiceAnalytics,
    WarrantyAnalytics,
    get_date_range_from_request,
    get_stall_from_request,
)
from clients.models import Client
from django.db.models import (
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Sum,
)
from django.db.models.functions import TruncDay
from django.utils import timezone
from django.utils.dateparse import parse_date
from expenses.models import Expense
from inventory.models import StockRoomStock
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from sales.models import SalesItem, SalesPayment, SalesTransaction


def get_date_range(request):
    start = request.query_params.get("start_date")
    end = request.query_params.get("end_date")

    start_date = parse_date(start) if start else (timezone.now().date() - timedelta(days=30))
    end_date = parse_date(end) if end else timezone.now().date()

    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_date, time.max))

    return start_dt, end_dt


def get_stall_filter(request):
    user = request.user
    stall_param = request.query_params.get("stall")

    if user.is_superuser or user.role == "admin":
        return {} if not stall_param else {"stall_id": stall_param}

    if user.role in ["manager", "clerk"]:
        return {"stall_id": user.assigned_stall}

    return {}


from inventory.models import Stock


class SummaryStatsView(APIView):
    def get(self, request):
        start_date, end_date = get_date_range(request)
        stall_filter = get_stall_filter(request)

        revenue = (
            SalesItem.objects.filter(
                transaction__created_at__range=(start_date, end_date),
                transaction__is_deleted=False,
            )
            .filter(**{"transaction__%s" % k: v for k, v in stall_filter.items()})
            .aggregate(total=Sum(F("quantity") * F("final_price_per_unit")))["total"]
            or 0
        )

        clients_count = Client.objects.all().count()

        # Determine if user is admin
        is_admin = request.user.is_staff

        if is_admin:
            stock_qs = StockRoomStock.objects.filter(is_deleted=False)

            no_stock_count = stock_qs.filter(quantity=0).count()
            low_stock_count = stock_qs.filter(
                quantity__gt=0, quantity__lte=F("low_stock_threshold")
            ).count()

        else:
            stock_qs = Stock.objects.filter(
                is_deleted=False, **stall_filter, track_stock=True
            )

            no_stock_count = stock_qs.filter(quantity=0).count()
            low_stock_count = stock_qs.filter(
                quantity__gt=0, quantity__lte=F("low_stock_threshold")
            ).count()

        expense = (
            Expense.objects.filter(
                created_at__range=(start_date, end_date),
                is_deleted=False,
            )
            .filter(**stall_filter)
            .aggregate(total=Sum("total_price"))["total"]
            or 0
        )

        net_income = (
            SalesItem.objects.filter(
                transaction__created_at__range=(start_date, end_date),
                transaction__is_deleted=False,
                **{"transaction__%s" % k: v for k, v in stall_filter.items()}
            ).aggregate(
                total=Sum(
                    ExpressionWrapper(
                        F("quantity") * F("final_price_per_unit"),
                        output_field=FloatField(),
                    )
                )
            )[
                "total"
            ]
            or 0
        )

        top_selling_item = (
            SalesItem.objects.filter(
                transaction__created_at__range=(start_date, end_date),
                transaction__is_deleted=False,
                **{"transaction__%s" % k: v for k, v in stall_filter.items()}
            )
            .values("item__name")
            .annotate(total_sold=Sum("quantity"))
            .order_by("-total_sold")
            .first()
        )

        expense_count = Expense.objects.filter(
            created_at__range=(start_date, end_date), is_deleted=False, **stall_filter
        ).count()

        return Response(
            {
                "total_sales": float(revenue),
                "total_clients": clients_count,
                "low_stock_items": low_stock_count,
                "no_stock_items": no_stock_count,
                "total_expense": float(expense),
                "net_income": float(net_income) - float(expense),
                "top_selling_item": {
                    "name": (
                        top_selling_item["item__name"] if top_selling_item else None
                    ),
                    "quantity": (
                        top_selling_item["total_sold"] if top_selling_item else 0
                    ),
                },
                "expense_count": expense_count,
            }
        )


class SalesOverTimeView(APIView):
    def get(self, request):
        start_date, end_date = get_date_range(request)
        stall_filter = get_stall_filter(request)

        queryset = (
            SalesItem.objects.filter(
                transaction__created_at__range=(start_date, end_date),
                transaction__is_deleted=False,
            )
            .filter(**{"transaction__%s" % k: v for k, v in stall_filter.items()})
            .annotate(day=TruncDay("transaction__created_at"))
            .values("day")
            .annotate(total_sales=Sum(F("quantity") * F("final_price_per_unit")))
            .order_by("day")
        )

        return Response(
            [
                {"date": q["day"], "total_sales": float(q["total_sales"] or 0)}
                for q in queryset
            ]
        )


class ExpensesOverTimeView(APIView):
    def get(self, request):
        start_date, end_date = get_date_range(request)
        stall_filter = get_stall_filter(request)

        queryset = (
            Expense.objects.filter(
                created_at__range=(start_date, end_date), is_deleted=False
            )
            .filter(**stall_filter)
            .annotate(day=TruncDay("created_at"))
            .values("day")
            .annotate(total_expense=Sum("total_price"))
            .order_by("day")
        )

        return Response(
            [
                {"date": q["day"], "total_expense": float(q["total_expense"] or 0)}
                for q in queryset
            ]
        )


class TopSellingItemsView(APIView):
    def get(self, request):
        start_date, end_date = get_date_range(request)
        stall_filter = get_stall_filter(request)
        limit = int(request.query_params.get("limit", 10))

        queryset = (
            SalesItem.objects.filter(
                transaction__created_at__range=(start_date, end_date),
                transaction__is_deleted=False,
            )
            .filter(**{"transaction__%s" % k: v for k, v in stall_filter.items()})
            .values("item__name")
            .annotate(total_quantity=Sum("quantity"))
            .order_by("-total_quantity")[:limit]
        )

        return Response(
            [
                {"item": q["item__name"], "quantity": q["total_quantity"]}
                for q in queryset
            ]
        )


class CashFlowView(APIView):
    def get(self, request):
        start_date, end_date = get_date_range(request)
        stall_filter = get_stall_filter(request)

        payments = (
            SalesPayment.objects.filter(payment_date__range=(start_date, end_date))
            .filter(**{"transaction__%s" % k: v for k, v in stall_filter.items()})
            .annotate(day=TruncDay("payment_date"))
            .values("day")
            .annotate(income=Sum("amount"))
        )

        expenses = (
            Expense.objects.filter(
                created_at__range=(start_date, end_date), is_deleted=False
            )
            .filter(**stall_filter)
            .annotate(day=TruncDay("created_at"))
            .values("day")
            .annotate(expense=Sum("total_price"))
        )

        data = {}
        for p in payments:
            data.setdefault(p["day"], {}).update({"income": float(p["income"] or 0)})
        for e in expenses:
            data.setdefault(e["day"], {}).update({"expense": float(e["expense"] or 0)})

        return Response(
            [
                {
                    "date": day,
                    "income": v.get("income", 0),
                    "expense": v.get("expense", 0),
                }
                for day, v in sorted(data.items())
            ]
        )


class TopClientsView(APIView):
    def get(self, request):
        start_date, end_date = get_date_range(request)
        stall_filter = get_stall_filter(request)
        limit = int(request.query_params.get("limit", 10))

        queryset = (
            SalesTransaction.objects.filter(
                is_deleted=False,
                client__isnull=False,
                created_at__range=(start_date, end_date),
            )
            .filter(**stall_filter)
            .values("client__full_name")
            .annotate(
                total_spent=Sum(F("items__quantity") * F("items__final_price_per_unit"))
            )
            .order_by("-total_spent")[:limit]
        )

        return Response(
            [
                {
                    "client": q["client__full_name"],
                    "total_spent": float(q["total_spent"] or 0),
                }
                for q in queryset
            ]
        )


class UnpaidSalesStatusView(APIView):
    def get(self, request):
        start_date, end_date = get_date_range(request)
        stall_filter = get_stall_filter(request)

        queryset = (
            SalesTransaction.objects.filter(
                is_deleted=False, created_at__range=(start_date, end_date)
            )
            .filter(**stall_filter)
            .values("payment_status")
            .annotate(count=Count("id"))
        )

        return Response(
            [{"status": q["payment_status"], "count": q["count"]} for q in queryset]
        )


# ----------------------------------
# New Comprehensive Analytics Views
# ----------------------------------
class AnalyticsViewSet(ViewSet):
    """
    Comprehensive analytics endpoints.

    Provides analytics for:
    - Revenue (sales + services)
    - Payment collections
    - Outstanding balances and aging
    - Service performance
    - Technician productivity
    - Warranty claims
    - Client behavior
    - Inventory turnover
    - Dashboard summaries
    """

    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="revenue-summary")
    def revenue_summary(self, request):
        """
        Get revenue summary for sales and services.

        Query params:
        - start_date: YYYY-MM-DD (default: 30 days ago)
        - end_date: YYYY-MM-DD (default: today)
        - stall: Stall ID (optional)

        Returns comprehensive revenue breakdown.
        """
        start_date, end_date = get_date_range_from_request(request)
        stall = get_stall_from_request(request)

        data = RevenueAnalytics.get_revenue_summary(start_date, end_date, stall)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="revenue-over-time")
    def revenue_over_time(self, request):
        """
        Get revenue over time (daily, weekly, or monthly).

        Query params:
        - start_date, end_date, stall (as above)
        - period: 'day', 'week', or 'month' (default: 'day')

        Returns time-series revenue data.
        """
        start_date, end_date = get_date_range_from_request(request)
        stall = get_stall_from_request(request)
        period = request.query_params.get("period", "day")

        data = RevenueAnalytics.get_revenue_over_time(start_date, end_date, stall, period)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="payment-collections")
    def payment_collections(self, request):
        """
        Get payment collection summary.

        Query params:
        - start_date, end_date, stall

        Returns total collections from sales and services.
        """
        start_date, end_date = get_date_range_from_request(request)
        stall = get_stall_from_request(request)

        data = PaymentAnalytics.get_collection_summary(start_date, end_date, stall)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="payment-methods")
    def payment_methods(self, request):
        """
        Get payment method breakdown.

        Query params:
        - start_date, end_date, stall

        Returns breakdown by payment type (cash, gcash, etc.).
        """
        start_date, end_date = get_date_range_from_request(request)
        stall = get_stall_from_request(request)

        data = PaymentAnalytics.get_payment_method_breakdown(start_date, end_date, stall)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="outstanding-summary")
    def outstanding_summary(self, request):
        """
        Get outstanding balance summary.

        Query params:
        - stall (optional)

        Returns outstanding balances for sales and services.
        """
        stall = get_stall_from_request(request)

        data = OutstandingAnalytics.get_outstanding_summary(stall)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="aging-report")
    def aging_report(self, request):
        """
        Get aging report for outstanding balances.

        Query params:
        - stall (optional)

        Returns balances bucketed by age (0-30, 31-60, 61-90, 90+ days).
        """
        stall = get_stall_from_request(request)

        data = OutstandingAnalytics.get_aging_report(stall)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="service-summary")
    def service_summary(self, request):
        """
        Get service performance summary.

        Query params:
        - start_date, end_date, stall

        Returns service metrics including completion rates and revenue.
        """
        start_date, end_date = get_date_range_from_request(request)
        stall = get_stall_from_request(request)

        data = ServiceAnalytics.get_service_summary(start_date, end_date, stall)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="technician-productivity")
    def technician_productivity(self, request):
        """
        Get technician productivity report.

        Query params:
        - start_date, end_date

        Returns productivity metrics for each technician.
        """
        start_date, end_date = get_date_range_from_request(request)

        data = ServiceAnalytics.get_technician_productivity(start_date, end_date)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="warranty-summary")
    def warranty_summary(self, request):
        """
        Get warranty claims summary.

        Query params:
        - start_date, end_date

        Returns warranty claim metrics and costs.
        """
        start_date, end_date = get_date_range_from_request(request)

        data = WarrantyAnalytics.get_warranty_summary(start_date, end_date)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="top-clients")
    def top_clients(self, request):
        """
        Get top clients by spending.

        Query params:
        - start_date, end_date
        - limit: Number of clients to return (default: 10)

        Returns top clients ranked by total spending.
        """
        start_date, end_date = get_date_range_from_request(request)
        limit = int(request.query_params.get("limit", 10))

        data = ClientAnalytics.get_top_clients(start_date, end_date, limit)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="inventory-summary")
    def inventory_summary(self, request):
        """
        Get inventory health summary.

        Query params:
        - stall (optional)

        Returns inventory metrics including stock levels and value.
        """
        stall = get_stall_from_request(request)

        data = InventoryAnalytics.get_inventory_summary(stall)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="stock-turnover")
    def stock_turnover(self, request):
        """
        Get stock turnover analysis.

        Query params:
        - start_date, end_date
        - limit: Number of items to return (default: 20)

        Returns items ranked by movement/turnover.
        """
        start_date, end_date = get_date_range_from_request(request)
        limit = int(request.query_params.get("limit", 20))

        data = InventoryAnalytics.get_stock_turnover(start_date, end_date, limit)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request):
        """
        Get consolidated dashboard summary.

        Query params:
        - start_date, end_date, stall

        Returns comprehensive dashboard data including:
        - Revenue summary
        - Collection summary
        - Outstanding balances
        - Service metrics
        - Inventory health
        """
        start_date, end_date = get_date_range_from_request(request)
        stall = get_stall_from_request(request)

        data = DashboardAnalytics.get_dashboard_summary(start_date, end_date, stall)
        return Response(data, status=status.HTTP_200_OK)
