from datetime import datetime, time, timedelta

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
from inventory.models import Stock, StockRoomStock
from payroll.models import Holiday
from rest_framework.response import Response
from rest_framework.views import APIView
from sales.models import SalesItem, SalesPayment, SalesTransaction
from schedules.models import Schedule
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
        return {"stall_id": user.assigned_stall}

    return {}


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


class CalendarEventsView(APIView):
    """
    API endpoint for fetching calendar events (birthdays, holidays, schedules)
    Supports multiple technicians per schedule

    Query Parameters:
        - start: Start date (ISO format)
        - end: End date (ISO format)
        - event_types: Comma-separated list of event types (birthday, holiday, schedule)
        - technician_ids: Comma-separated list of technician IDs
        - service_type: Filter schedules by service type
    """

    def get(self, request):
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

        # Additional filters
        technician_ids_param = request.query_params.get("technician_ids")
        service_type = request.query_params.get("service_type")

        events = []

        # Fetch birthdays
        if include_birthdays:
            birthdays = CustomUser.objects.filter(
                is_deleted=False,
                birthday__isnull=False
            ).values('id', 'first_name', 'last_name', 'birthday')

            for user in birthdays:
                # Calculate birthday for current year range
                birthday = user['birthday']
                year_start = start_date.year
                year_end = end_date.year

                for year in range(year_start, year_end + 1):
                    birthday_this_year = birthday.replace(year=year)
                    if start_date <= birthday_this_year <= end_date:
                        events.append({
                            'id': f"birthday-{user['id']}-{year}",
                            'title': f"{user['first_name']} {user['last_name']}'s Birthday",
                            'start': birthday_this_year.isoformat(),
                            'end': birthday_this_year.isoformat(),
                            'allDay': True,
                            'extendedProps': {
                                'type': 'birthday',
                                'user_id': user['id'],
                                'user_name': f"{user['first_name']} {user['last_name']}",
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
                scheduled_datetime__date__gte=start_date,
                scheduled_datetime__date__lte=end_date
            ).prefetch_related('technicians', 'client')

            # Apply additional filters
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

                # Get display name for service type
                service_type_dict = dict(Schedule.SERVICE_TYPES)
                service_display = service_type_dict.get(schedule.service_type, schedule.service_type)

                # Create title
                tech_display = ", ".join(technician_names) if technician_names else "Unassigned"
                title = f"{service_display} - {schedule.client.full_name}"
                if technician_names:
                    title += f" ({tech_display})"

                events.append({
                    'id': f"schedule-{schedule.id}",
                    'title': title,
                    'start': schedule.scheduled_datetime.isoformat(),
                    'allDay': False,
                    'extendedProps': {
                        'type': 'schedule',
                        'schedule_id': schedule.id,
                        'service_type': schedule.service_type,
                        'service_type_display': service_display,
                        'client_name': schedule.client.full_name,
                        'client_id': schedule.client.id,
                        'technician_names': technician_names,
                        'technician_ids': technician_ids,
                        'technician_display': tech_display,
                        'technician_count': len(technician_names),
                        'notes': schedule.notes,
                    }
                })

        return Response(events)
