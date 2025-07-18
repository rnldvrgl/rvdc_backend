from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models.functions import TruncDay
from django.utils.timezone import now
from django.utils.dateparse import parse_date
from datetime import datetime, time, timedelta
from django.db.models import (
    Avg,
    Sum,
    F,
    FloatField,
    ExpressionWrapper,
    Sum,
    F,
    Count,
)

from sales.models import SalesItem, SalesTransaction, SalesPayment
from expenses.models import Expense
from inventory.models import StockTransfer, StockRoomStock
from clients.models import Client


def get_date_range(request):
    start = request.query_params.get("start_date")
    end = request.query_params.get("end_date")

    start_date = parse_date(start) if start else (now().date() - timedelta(days=30))
    end_date = parse_date(end) if end else now().date()

    # convert to datetime objects with proper range inclusion
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

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
        else:
            stock_qs = Stock.objects.filter(is_deleted=False, **stall_filter)

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


class RestocksOverTimeView(APIView):
    def get(self, request):
        start_date, end_date = get_date_range(request)
        stall_filter = get_stall_filter(request)

        queryset = (
            StockTransfer.objects.filter(created_at__range=(start_date, end_date))
            .filter(**stall_filter)
            .annotate(day=TruncDay("created_at"))
            .values("day")
            .annotate(restocked_items=Sum("items__quantity"))
            .order_by("day")
        )

        return Response(
            [
                {"date": q["day"], "restock_volume": q["restocked_items"] or 0}
                for q in queryset
            ]
        )
