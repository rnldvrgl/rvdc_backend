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
from attendance.models import LeaveRequest, HalfDaySchedule
from clients.models import Client
from django.db.models import (
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Q,
    Sum,
)
from django.db.models.functions import TruncDay
from django.utils import timezone
from django.utils.dateparse import parse_date
from expenses.models import Expense
from inventory.models import Stock, StockRoomStock
from payroll.models import Holiday
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from sales.models import SalesItem, SalesPayment, SalesTransaction
from schedules.models import Schedule
from services.models import Service, ServicePayment
from users.models import CustomUser


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
        if user.assigned_stall_id:
            return {"stall_id": user.assigned_stall_id}
        return {}

    return {}


class SummaryStatsView(APIView):
    def get(self, request):
        from decimal import Decimal
        
        start_date, end_date = get_date_range(request)
        stall_filter = get_stall_filter(request)
        today = timezone.now().date()

        # Sales revenue
        sales_revenue = (
            SalesItem.objects.filter(
                transaction__created_at__range=(start_date, end_date),
                transaction__is_deleted=False,
            )
            .filter(**{"transaction__%s" % k: v for k, v in stall_filter.items()})
            .aggregate(total=Sum(F("quantity") * F("final_price_per_unit")))["total"]
            or 0
        )

        # Service revenue
        service_qs = Service.objects.filter(
            created_at__date__gte=start_date.date() if hasattr(start_date, 'date') else start_date,
            created_at__date__lte=end_date.date() if hasattr(end_date, 'date') else end_date,
        )
        if stall_filter:
            service_qs = service_qs.filter(**stall_filter)
        
        service_revenue = service_qs.aggregate(total=Sum("total_revenue"))["total"] or Decimal("0")

        # Total revenue (sales + services)
        total_revenue = float(sales_revenue) + float(service_revenue)

        # Clients
        clients_count = Client.objects.filter(is_deleted=False).count()
        
        # New clients in period
        new_clients = Client.objects.filter(
            created_at__range=(start_date, end_date),
            is_deleted=False
        ).count()

        # Stock inventory
        user = request.user
        is_admin = user.is_superuser or user.role == "admin"

        if is_admin:
            stock_qs = StockRoomStock.objects.filter(is_deleted=False)
            no_stock_count = stock_qs.filter(quantity=0).count()
            low_stock_count = stock_qs.filter(
                quantity__gt=0, quantity__lte=F("low_stock_threshold")
            ).count()
        else:
            stock_qs = Stock.objects.filter(
                is_deleted=False, track_stock=True, **stall_filter
            )
            no_stock_count = stock_qs.filter(quantity=0).count()
            low_stock_count = stock_qs.filter(
                quantity__gt=0, quantity__lte=F("low_stock_threshold")
            ).count()

        # Expenses
        expense = (
            Expense.objects.filter(
                created_at__range=(start_date, end_date),
                is_deleted=False,
            )
            .filter(**stall_filter)
            .aggregate(total=Sum("total_price"))["total"]
            or 0
        )

        # Net income
        net_income = total_revenue - float(expense)

        # Outstanding balances
        # Calculate sales outstanding
        # Total due from unpaid/partial transactions
        sales_total_due = SalesTransaction.objects.filter(
            is_deleted=False,
            voided=False,
            payment_status__in=['partial', 'unpaid']
        ).annotate(
            total=Sum(F('items__quantity') * F('items__final_price_per_unit'))
        ).aggregate(
            total_due=Sum('total')
        )['total_due'] or Decimal("0")
        
        # Total paid for those transactions
        sales_total_paid = SalesPayment.objects.filter(
            transaction__is_deleted=False,
            transaction__voided=False,
            transaction__payment_status__in=['partial', 'unpaid']
        ).aggregate(
            total_paid=Sum('amount')
        )['total_paid'] or Decimal("0")
        
        sales_outstanding = sales_total_due - sales_total_paid
        
        # Calculate services outstanding
        # Total revenue from unpaid/partial services
        services_total_due = Service.objects.filter(
            payment_status__in=['partial', 'unpaid']
        ).aggregate(
            total_due=Sum('total_revenue')
        )['total_due'] or Decimal("0")
        
        # Total paid for those services
        services_total_paid = ServicePayment.objects.filter(
            service__payment_status__in=['partial', 'unpaid']
        ).aggregate(
            total_paid=Sum('amount')
        )['total_paid'] or Decimal("0")
        
        services_outstanding = services_total_due - services_total_paid
        
        total_outstanding = float(sales_outstanding) + float(services_outstanding)

        # Service metrics
        service_stats = Service.objects.filter(
            created_at__date__gte=start_date.date() if hasattr(start_date, 'date') else start_date,
            created_at__date__lte=end_date.date() if hasattr(end_date, 'date') else end_date,
        ).aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            active=Count('id', filter=Q(status__in=['pending', 'in_progress', 'confirmed']))
        )
        
        completion_rate = (
            (service_stats['completed'] / service_stats['total'] * 100)
            if service_stats['total'] > 0 else 0
        )

        # Schedule metrics
        pending_schedules = Schedule.objects.filter(
            scheduled_date=today,
            status='pending'
        ).count()
        
        today_schedules = Schedule.objects.filter(
            scheduled_date=today
        ).count()

        # Top selling item
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

        return Response(
            {
                # Revenue metrics
                "total_sales": float(sales_revenue),
                "service_revenue": float(service_revenue),
                "total_revenue": total_revenue,
                "net_income": net_income,
                
                # Outstanding balances
                "total_outstanding": total_outstanding,
                "sales_outstanding": float(sales_outstanding),
                "services_outstanding": float(services_outstanding),
                
                # Service performance
                "total_services": service_stats['total'],
                "active_services": service_stats['active'],
                "completed_services": service_stats['completed'],
                "service_completion_rate": round(completion_rate, 1),
                
                # Schedule metrics
                "today_schedules": today_schedules,
                "pending_schedules": pending_schedules,
                
                # Client metrics
                "total_clients": clients_count,
                "new_clients": new_clients,
                
                # Inventory
                "low_stock_items": low_stock_count,
                "no_stock_items": no_stock_count,
                "inventory_alerts": low_stock_count + no_stock_count,
                
                # Expenses
                "total_expense": float(expense),
                
                # Top selling
                "top_selling_item": {
                    "name": (
                        top_selling_item["item__name"] if top_selling_item else None
                    ),
                    "quantity": (
                        top_selling_item["total_sold"] if top_selling_item else 0
                    ),
                },
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


class CalendarEventsView(APIView):
    """
    API endpoint for fetching calendar events (birthdays, holidays, schedules, leaves, deliveries)
    Implements role-based filtering:
    - Technicians: Their birthdays, all holidays, schedules they're assigned to, their leaves, their deliveries
    - Clerks: All birthdays, all holidays, their leaves only
    - Managers/Admins: All events

    Query Parameters:
        - start: Start date (ISO format)
        - end: End date (ISO format)
        - event_types: Comma-separated list of event types (birthday, holiday, schedule, leave)
        - technician_ids: Comma-separated list of technician IDs (for manual filtering)
        - service_type: Filter schedules by service type
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Get current user and role
        user = request.user
        user_role = getattr(user, 'role', None)
        
        # Get date range from query params
        start_param = request.query_params.get("start")
        end_param = request.query_params.get("end")

        if start_param and end_param:
            start_date = parse_date(start_param)
            end_date = parse_date(end_param)
        else:
            # Default to current month if no dates provided
            now = timezone.now()
            start_date = now.date().replace(day=1)
            # Get last day of month
            if now.month == 12:
                end_date = now.date().replace(month=12, day=31)
            else:
                end_date = (now.date().replace(month=now.month + 1, day=1) - timedelta(days=1))

        # Get filter parameters
        event_types_param = request.query_params.get("event_types", "")
        event_types = [t.strip() for t in event_types_param.split(",")] if event_types_param else []

        # If no specific types requested, include all
        include_birthdays = not event_types or "birthday" in event_types
        include_holidays = not event_types or "holiday" in event_types
        include_schedules = not event_types or "schedule" in event_types
        include_leaves = not event_types or "leave" in event_types

        # Additional filters
        technician_ids_param = request.query_params.get("technician_ids")
        service_type = request.query_params.get("service_type")

        events = []

        # Fetch birthdays - Role-based filtering
        if include_birthdays:
            birthdays_query = CustomUser.objects.filter(
                is_deleted=False,
                birthday__isnull=False
            )
            
            birthdays = birthdays_query.values('id', 'first_name', 'last_name', 'birthday')

            for birthday_user in birthdays:
                # Calculate birthday for current year range
                birthday = birthday_user['birthday']
                year_start = start_date.year
                year_end = end_date.year

                for year in range(year_start, year_end + 1):
                    birthday_this_year = birthday.replace(year=year)
                    if start_date <= birthday_this_year <= end_date:
                        events.append({
                            'id': f"birthday-{birthday_user['id']}-{year}",
                            'title': f"{birthday_user['first_name']} {birthday_user['last_name']}'s Birthday",
                            'start': birthday_this_year.isoformat(),
                            'end': birthday_this_year.isoformat(),
                            'allDay': True,
                            'extendedProps': {
                                'type': 'birthday',
                                'user_id': birthday_user['id'],
                                'user_name': f"{birthday_user['first_name']} {birthday_user['last_name']}",
                            }
                        })

        # Fetch holidays
        if include_holidays:
            holidays = Holiday.objects.filter(
                is_deleted=False,
                date__gte=start_date,
                date__lte=end_date
            ).values('id', 'name', 'date', 'kind')

            for holiday in holidays:
                events.append({
                    'id': f"holiday-{holiday['id']}",
                    'title': holiday['name'],
                    'start': holiday['date'].isoformat(),
                    'end': holiday['date'].isoformat(),
                    'allDay': True,
                    'extendedProps': {
                        'type': 'holiday',
                        'holiday_id': holiday['id'],
                        'holiday_type': holiday['kind'],
                    }
                })

        # Fetch schedules with multiple technicians
        if include_schedules:
            schedules_query = Schedule.objects.filter(
                scheduled_date__gte=start_date,
                scheduled_date__lte=end_date
            ).prefetch_related('technicians', 'client', 'service')
            
            # Role-based filtering for schedules
            if user_role == 'technician':
                # Technicians see only schedules they are assigned to
                schedules_query = schedules_query.filter(technicians__id=user.id).distinct()
            elif user_role == 'clerk':
                # Clerks see no schedules
                schedules_query = Schedule.objects.none()
            # Managers and admins see all schedules (no additional filter)

            # Apply additional filters (after role-based filtering)
            if technician_ids_param:
                try:
                    tech_ids = [int(tid.strip()) for tid in technician_ids_param.split(',')]
                    schedules_query = schedules_query.filter(technicians__id__in=tech_ids).distinct()
                except ValueError:
                    pass

            if service_type:
                schedules_query = schedules_query.filter(service_type=service_type)

            for schedule in schedules_query:
                # Get all technician information
                technicians = schedule.technicians.all()
                technician_names = [tech.get_full_name() for tech in technicians]
                technician_ids = [tech.id for tech in technicians]

                # Get display name for schedule type
                schedule_type_dict = dict(Schedule.SCHEDULE_TYPES)
                schedule_display = schedule_type_dict.get(schedule.schedule_type, schedule.schedule_type)
    
                # Create title
                tech_display = ", ".join(technician_names) if technician_names else "Unassigned"
                title = f"{schedule_display} - {schedule.client.full_name}"
                if technician_names:
                    title += f" ({tech_display})"

                # Combine date and time for the event
                if schedule.scheduled_time:
                    # Combine date and time
                    scheduled_datetime = timezone.datetime.combine(
                        schedule.scheduled_date,
                        schedule.scheduled_time
                    )
                    # Make timezone-aware if needed
                    if timezone.is_naive(scheduled_datetime):
                        scheduled_datetime = timezone.make_aware(scheduled_datetime)
                    start_iso = scheduled_datetime.isoformat()
                    all_day = False
                else:
                    # No time specified, treat as all-day event
                    start_iso = schedule.scheduled_date.isoformat()
                    all_day = True

                # Debug logging
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Schedule {schedule.id}: scheduled_date={schedule.scheduled_date}, scheduled_time={schedule.scheduled_time}, start_iso={start_iso}")

                # Get service type if service is linked
                service_type = None
                service_type_display = None
                if schedule.service:
                    service_type = schedule.service.service_type
                    from utils.enums import ServiceType
                    service_type_display = ServiceType(service_type).label if service_type else None

                events.append({
                    'id': f"schedule-{schedule.id}",
                    'title': title,
                    'start': start_iso,
                    'allDay': all_day,
                    'extendedProps': {
                        'type': 'schedule',
                        'schedule_id': schedule.id,
                        'schedule_type': schedule.schedule_type,
                        'schedule_type_display': schedule_display,
                        'service_type': service_type,
                        'service_type_display': service_type_display,
                        'client_name': schedule.client.full_name,
                        'client_id': schedule.client.id,
                        'technician_names': technician_names,
                        'technician_ids': technician_ids,
                        'technician_display': tech_display,
                        'technician_count': len(technician_names),
                        'notes': schedule.notes,
                    }
                })
            
            # Also fetch delivery dates from services
            from services.models import Service
            
            services_query = Service.objects.filter(
                delivery_date__isnull=False,
                delivery_date__date__gte=start_date,
                delivery_date__date__lte=end_date
            ).select_related('client').prefetch_related('schedules__technicians')
            
            # Role-based filtering for delivery dates
            if user_role == 'technician':
                # Technicians see only their assigned services
                services_query = services_query.filter(
                    schedules__technicians__id=user.id
                ).distinct()
            elif user_role == 'clerk':
                # Clerks see no delivery dates
                services_query = Service.objects.none()
            # Managers and admins see all delivery dates
            
            for service in services_query:
                delivery_datetime = service.delivery_date
                delivery_date = delivery_datetime.date()
                delivery_time = delivery_datetime.time()
                
                # Check if delivery date is within range
                if start_date <= delivery_date <= end_date:
                    title = f"Delivery - {service.client.full_name}"
                    
                    # Use full datetime for the event
                    start_iso = delivery_datetime.isoformat()
                    
                    # Get technicians from related schedules
                    technician_names = []
                    technician_ids = []
                    schedules = service.schedules.all()
                    for schedule in schedules:
                        for tech in schedule.technicians.all():
                            tech_name = f"{tech.first_name} {tech.last_name}"
                            if tech_name not in technician_names:
                                technician_names.append(tech_name)
                                technician_ids.append(tech.id)
                    
                    # Get service type display
                    from utils.enums import ServiceType
                    service_type_display = ServiceType(service.service_type).label if service.service_type else None
                    
                    events.append({
                        'id': f"delivery-{service.id}",
                        'title': title,
                        'start': start_iso,
                        'allDay': False,
                        'extendedProps': {
                            'type': 'delivery',
                            'service_id': service.id,
                            'client_name': service.client.full_name,
                            'client_id': service.client.id,
                            'service_type': service.service_type,
                            'service_type_display': service_type_display,
                            'delivery_date': delivery_date.isoformat(),
                            'delivery_time': delivery_time.strftime('%H:%M'),
                            'technician_names': technician_names,
                            'technician_ids': technician_ids,
                            'notes': service.notes,
                        }
                    })

        # Fetch approved leaves (supports multi-day date ranges)
        if include_leaves:
            from django.db.models import Q
            
            # Filter leaves that overlap with the requested date range
            # A leave overlaps if: leave_start <= range_end AND leave_end >= range_start
            leaves_query = LeaveRequest.objects.filter(
                status='APPROVED',
            ).filter(
                # Overlap logic: handles both old (date only) and new (start_date/end_date) records
                Q(start_date__lte=end_date, end_date__gte=start_date) |  # Multi-day range overlap
                Q(start_date__isnull=True, date__gte=start_date, date__lte=end_date)  # Legacy single-date
            ).select_related('employee')
            
            # Role-based filtering for leaves
            if user_role in ['technician', 'clerk']:
                # Technicians and clerks see only their own leaves
                leaves_query = leaves_query.filter(employee=user)
            # Managers and admins see all leaves (no additional filter)
            
            leaves = leaves_query.values(
                'id', 'employee__first_name', 'employee__last_name',
                'employee_id', 'leave_type', 'date', 'start_date', 'end_date',
                'is_half_day', 'shift_period', 'reason', 'days_count'
            )

            for leave in leaves:
                # Get leave type display
                leave_type_display = dict(LeaveRequest.LEAVE_TYPE_CHOICES).get(
                    leave['leave_type'], leave['leave_type']
                )

                # Get shift period display
                shift_period_choices = {
                    'AM': 'Morning',
                    'PM': 'Afternoon',
                    'FULL': 'Full Day'
                }
                shift_display = shift_period_choices.get(leave['shift_period'], 'Full Day')

                # Determine start and end dates
                leave_start = leave['start_date'] or leave['date']
                leave_end = leave['end_date'] or leave['date']
                is_multi_day = leave_start != leave_end

                # Build title
                if is_multi_day:
                    days = leave['days_count'] or (leave_end - leave_start).days + 1
                    duration = f"{days} Day{'s' if float(str(days)) != 1 else ''}"
                else:
                    duration = f"Half Day - {shift_display}" if leave['is_half_day'] else "Full Day"

                employee_name = f"{leave['employee__first_name']} {leave['employee__last_name']}"
                title = f"{employee_name} - {leave_type_display} ({duration})"

                events.append({
                    'id': f"leave-{leave['id']}",
                    'title': title,
                    'start': leave_start.isoformat(),
                    'end': leave_end.isoformat(),
                    'allDay': True,
                    'extendedProps': {
                        'type': 'leave',
                        'leave_id': leave['id'],
                        'employee_id': leave['employee_id'],
                        'employee_name': employee_name,
                        'leave_type': leave['leave_type'],
                        'leave_type_display': leave_type_display,
                        'is_half_day': leave['is_half_day'],
                        'is_multi_day': is_multi_day,
                        'days_count': str(leave['days_count']) if leave['days_count'] else None,
                        'shift_period': leave['shift_period'],
                        'shift_period_display': shift_display,
                        'reason': leave['reason'],
                    }
                })
        
        # Fetch custom calendar events
        custom_events = CalendarEvent.objects.filter(
            is_deleted=False,
            event_date__gte=start_date,
            event_date__lte=end_date
        ).select_related('created_by').values(
            'id', 'title', 'description', 'event_date', 'event_type', 'created_by__first_name', 'created_by__last_name'
        )
        
        for custom_event in custom_events:
            # Map event_type to color - distinguished colors
            type_colors = {
                'meeting': '#06b6d4',  # cyan-500
                'maintenance': '#eab308',  # yellow-500
                'training': '#a855f7',  # purple-500
                'deadline': '#f43f5e',  # rose-500
                'other': '#64748b',  # slate-500
            }
            
            events.append({
                'id': f"custom-{custom_event['id']}",
                'title': custom_event['title'],
                'start': custom_event['event_date'].isoformat(),
                'color': type_colors.get(custom_event['event_type'], '#6b7280'),
                'extendedProps': {
                    'type': 'custom_event',
                    'custom_event_id': custom_event['id'],
                    'description': custom_event['description'],
                    'event_type': custom_event['event_type'],
                    'created_by': f"{custom_event['created_by__first_name']} {custom_event['created_by__last_name']}",
                }
            })

        # Fetch half-day schedules
        half_day_schedules = HalfDaySchedule.objects.filter(
            is_deleted=False,
            date__gte=start_date,
            date__lte=end_date
        ).select_related('created_by').values(
            'id', 'date', 'reason', 'created_by__first_name', 'created_by__last_name'
        )
        
        for half_day in half_day_schedules:
            reason = half_day['reason'] or 'Half Day'
            events.append({
                'id': f"halfday-{half_day['id']}",
                'title': f"Half Day - {reason}",
                'start': half_day['date'].isoformat(),
                'end': half_day['date'].isoformat(),
                'allDay': True,
                'extendedProps': {
                    'type': 'half_day',
                    'half_day_id': half_day['id'],
                    'reason': reason,
                    'created_by': f"{half_day['created_by__first_name']} {half_day['created_by__last_name']}",
                }
            })

        return Response(events)


# ------------------------------------------------------------------------------
# Calendar Events
# ------------------------------------------------------------------------------

from analytics.api.serializers import CalendarEventSerializer, CalendarEventListSerializer
from analytics.models import CalendarEvent
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters


class CalendarEventViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing custom calendar events.
    
    Endpoints:
    - GET /api/analytics/calendar-events/ - List all events
    - POST /api/analytics/calendar-events/ - Create new event
    - GET /api/analytics/calendar-events/<id>/ - Retrieve specific event
    - PUT/PATCH /api/analytics/calendar-events/<id>/ - Update event
    - DELETE /api/analytics/calendar-events/<id>/ - Soft delete event
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CalendarEventSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['event_type', 'event_date', 'created_by']
    search_fields = ['title', 'description']
    ordering_fields = ['event_date', 'created_at', 'title']
    ordering = ['-event_date']
    
    def get_queryset(self):
        """Get non-deleted calendar events."""
        queryset = CalendarEvent.objects.filter(is_deleted=False).select_related('created_by')
        
        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(event_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(event_date__lte=end_date)
        
        return queryset
    
    def get_serializer_class(self):
        """Use lightweight serializer for list view."""
        if self.action == 'list':
            return CalendarEventListSerializer
        return CalendarEventSerializer
    
    def perform_destroy(self, instance):
        """Soft delete calendar event."""
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted'])

