"""
Analytics Business Logic

This module provides comprehensive analytics and reporting functionality for:
- Revenue analytics (sales + services)
- Payment analytics (collection reports, payment method analysis)
- Service analytics (completion rates, technician productivity)
- Outstanding balance tracking (aging reports)
- Warranty analytics (cost analysis, claim patterns)
- Inventory analytics (turnover, stock levels)
- Client analytics (customer behavior, top clients)
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import (
    Avg,
    Case,
    Count,
    DecimalField,
    F,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, TruncDate, TruncMonth, TruncWeek
from django.utils import timezone


# ----------------------------------
# Revenue Analytics
# ----------------------------------
class RevenueAnalytics:
    """Analytics for revenue from sales and services."""

    @staticmethod
    def get_revenue_summary(start_date=None, end_date=None, stall=None):
        """
        Get comprehensive revenue summary.

        Returns:
            dict with sales revenue, service revenue, total revenue, breakdowns
        """
        from sales.models import SalesTransaction
        from services.models import Service

        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()

        # Sales revenue
        sales_qs = SalesTransaction.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            is_deleted=False,
            voided=False,
        )
        if stall:
            sales_qs = sales_qs.filter(stall=stall)

        sales_aggregates = sales_qs.aggregate(
            total_sales=Count("id"),
            total_revenue=Sum(
                F("items__quantity") * F("items__final_price_per_unit")
            ),
            avg_sale=Avg(
                F("items__quantity") * F("items__final_price_per_unit")
            ),
        )

        # Service revenue
        service_qs = Service.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        if stall:
            service_qs = service_qs.filter(stall=stall)

        service_aggregates = service_qs.aggregate(
            total_services=Count("id"),
            total_revenue=Sum("total_revenue"),
            main_stall_revenue=Sum("main_stall_revenue"),
            sub_stall_revenue=Sum("sub_stall_revenue"),
            avg_service=Avg("total_revenue"),
        )

        # Combined totals
        sales_revenue = sales_aggregates["total_revenue"] or Decimal("0")
        service_revenue = service_aggregates["total_revenue"] or Decimal("0")
        total_revenue = sales_revenue + service_revenue

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "stall": stall.name if stall else "All Stalls",
            "sales": {
                "count": sales_aggregates["total_sales"] or 0,
                "revenue": float(sales_revenue),
                "average": float(sales_aggregates["avg_sale"] or 0),
            },
            "services": {
                "count": service_aggregates["total_services"] or 0,
                "revenue": float(service_revenue),
                "main_stall_revenue": float(service_aggregates["main_stall_revenue"] or 0),
                "sub_stall_revenue": float(service_aggregates["sub_stall_revenue"] or 0),
                "average": float(service_aggregates["avg_service"] or 0),
            },
            "total_revenue": float(total_revenue),
            "revenue_breakdown": {
                "sales_percentage": float((sales_revenue / total_revenue * 100) if total_revenue > 0 else 0),
                "services_percentage": float((service_revenue / total_revenue * 100) if total_revenue > 0 else 0),
            },
        }

    @staticmethod
    def get_revenue_over_time(start_date=None, end_date=None, stall=None, period="day"):
        """
        Get revenue over time (daily, weekly, or monthly).

        Args:
            period: 'day', 'week', or 'month'

        Returns:
            list of dicts with date and revenue amounts
        """
        from sales.models import SalesItem
        from services.models import Service

        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()

        # Choose truncation function
        trunc_func = {
            "day": TruncDate,
            "week": TruncWeek,
            "month": TruncMonth,
        }.get(period, TruncDate)

        # Sales over time
        sales_qs = SalesItem.objects.filter(
            transaction__created_at__date__gte=start_date,
            transaction__created_at__date__lte=end_date,
            transaction__is_deleted=False,
            transaction__voided=False,
        )
        if stall:
            sales_qs = sales_qs.filter(transaction__stall=stall)

        sales_data = (
            sales_qs.annotate(period=trunc_func("transaction__created_at"))
            .values("period")
            .annotate(sales_revenue=Sum(F("quantity") * F("final_price_per_unit")))
            .order_by("period")
        )

        # Services over time
        service_qs = Service.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        if stall:
            service_qs = service_qs.filter(stall=stall)

        service_data = (
            service_qs.annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(service_revenue=Sum("total_revenue"))
            .order_by("period")
        )

        # Combine data
        combined = {}
        for item in sales_data:
            date = item["period"]
            combined.setdefault(date, {})["sales_revenue"] = float(item["sales_revenue"] or 0)

        for item in service_data:
            date = item["period"]
            combined.setdefault(date, {})["service_revenue"] = float(item["service_revenue"] or 0)

        # Format result
        result = []
        for date, revenues in sorted(combined.items()):
            sales_rev = revenues.get("sales_revenue", 0)
            service_rev = revenues.get("service_revenue", 0)
            result.append({
                "date": date.isoformat() if hasattr(date, "isoformat") else str(date),
                "sales_revenue": sales_rev,
                "service_revenue": service_rev,
                "total_revenue": sales_rev + service_rev,
            })

        return result


# ----------------------------------
# Payment Analytics
# ----------------------------------
class PaymentAnalytics:
    """Analytics for payment collection and patterns."""

    @staticmethod
    def get_collection_summary(start_date=None, end_date=None, stall=None):
        """Get payment collection summary."""
        from sales.models import SalesPayment
        from services.models import ServicePayment

        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()

        # Sales payments
        sales_payments_qs = SalesPayment.objects.filter(
            payment_date__date__gte=start_date,
            payment_date__date__lte=end_date,
            transaction__voided=False,
            transaction__is_deleted=False,
        )
        if stall:
            sales_payments_qs = sales_payments_qs.filter(transaction__stall=stall)

        sales_payments = sales_payments_qs.aggregate(
            total_count=Count("id"),
            total_amount=Sum("amount"),
        )

        # Service payments
        service_payments_qs = ServicePayment.objects.filter(
            payment_date__date__gte=start_date,
            payment_date__date__lte=end_date,
        )
        if stall:
            service_payments_qs = service_payments_qs.filter(service__stall=stall)

        service_payments = service_payments_qs.aggregate(
            total_count=Count("id"),
            total_amount=Sum("amount"),
        )

        total_collected = (
            (sales_payments["total_amount"] or Decimal("0")) +
            (service_payments["total_amount"] or Decimal("0"))
        )

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "sales_payments": {
                "count": sales_payments["total_count"] or 0,
                "amount": float(sales_payments["total_amount"] or 0),
            },
            "service_payments": {
                "count": service_payments["total_count"] or 0,
                "amount": float(service_payments["total_amount"] or 0),
            },
            "total_collected": float(total_collected),
            "total_transactions": (
                (sales_payments["total_count"] or 0) +
                (service_payments["total_count"] or 0)
            ),
        }

    @staticmethod
    def get_payment_method_breakdown(start_date=None, end_date=None, stall=None):
        """Get breakdown of payments by payment method."""
        from sales.models import SalesPayment
        from services.models import ServicePayment

        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()

        # Sales payments by type
        sales_qs = SalesPayment.objects.filter(
            payment_date__date__gte=start_date,
            payment_date__date__lte=end_date,
            transaction__voided=False,
            transaction__is_deleted=False,
        )
        if stall:
            sales_qs = sales_qs.filter(transaction__stall=stall)

        sales_by_type = sales_qs.values("payment_type").annotate(
            count=Count("id"),
            amount=Sum("amount"),
        )

        # Service payments by type
        service_qs = ServicePayment.objects.filter(
            payment_date__date__gte=start_date,
            payment_date__date__lte=end_date,
        )
        if stall:
            service_qs = service_qs.filter(service__stall=stall)

        service_by_type = service_qs.values("payment_type").annotate(
            count=Count("id"),
            amount=Sum("amount"),
        )

        # Combine by payment type
        combined = {}
        for item in sales_by_type:
            ptype = item["payment_type"]
            combined.setdefault(ptype, {"count": 0, "amount": Decimal("0")})
            combined[ptype]["count"] += item["count"]
            combined[ptype]["amount"] += item["amount"] or Decimal("0")

        for item in service_by_type:
            ptype = item["payment_type"]
            combined.setdefault(ptype, {"count": 0, "amount": Decimal("0")})
            combined[ptype]["count"] += item["count"]
            combined[ptype]["amount"] += item["amount"] or Decimal("0")

        # Calculate total for percentages
        total_amount = sum(v["amount"] for v in combined.values())

        result = []
        for payment_type, data in combined.items():
            amount = data["amount"]
            result.append({
                "payment_type": payment_type,
                "count": data["count"],
                "amount": float(amount),
                "percentage": float((amount / total_amount * 100) if total_amount > 0 else 0),
            })

        return sorted(result, key=lambda x: x["amount"], reverse=True)


# ----------------------------------
# Outstanding Balance Analytics
# ----------------------------------
class OutstandingAnalytics:
    """Analytics for outstanding balances and aging."""

    @staticmethod
    def get_outstanding_summary(stall=None):
        """Get summary of outstanding balances."""
        from sales.models import PaymentStatus as SalesPaymentStatus
        from sales.models import SalesTransaction
        from services.models import PaymentStatus as ServicePaymentStatus
        from services.models import Service

        # Outstanding sales (exclude service-linked transactions to avoid double-counting with services)
        sales_qs = SalesTransaction.objects.filter(
            is_deleted=False,
            voided=False,
            payment_status__in=[SalesPaymentStatus.UNPAID, SalesPaymentStatus.PARTIAL],
        ).exclude(transaction_type='service')
        if stall:
            sales_qs = sales_qs.filter(stall=stall)

        sales_outstanding = sales_qs.aggregate(
            count=Count("id"),
            total_revenue=Sum(
                F("items__quantity") * F("items__final_price_per_unit")
            ),
            total_paid=Sum("payments__amount"),
        )

        sales_balance = (
            (sales_outstanding["total_revenue"] or Decimal("0")) -
            (sales_outstanding["total_paid"] or Decimal("0"))
        )

        # Outstanding services
        service_qs = Service.objects.filter(
            is_deleted=False,
            payment_status__in=[ServicePaymentStatus.UNPAID, ServicePaymentStatus.PARTIAL],
        ).exclude(status='cancelled')
        if stall:
            service_qs = service_qs.filter(stall=stall)

        service_outstanding = service_qs.aggregate(
            count=Count("id"),
            total_revenue=Sum("total_revenue"),
            total_paid=Sum("payments__amount"),
            total_refunded=Sum("total_refunded"),
        )

        service_balance = (
            (service_outstanding["total_revenue"] or Decimal("0")) -
            ((service_outstanding["total_paid"] or Decimal("0")) - (service_outstanding["total_refunded"] or Decimal("0")))
        )

        return {
            "sales": {
                "count": sales_outstanding["count"] or 0,
                "total_revenue": float(sales_outstanding["total_revenue"] or 0),
                "total_paid": float(sales_outstanding["total_paid"] or 0),
                "balance_due": float(sales_balance),
            },
            "services": {
                "count": service_outstanding["count"] or 0,
                "total_revenue": float(service_outstanding["total_revenue"] or 0),
                "total_paid": float(service_outstanding["total_paid"] or 0),
                "total_refunded": float(service_outstanding["total_refunded"] or 0),
                "balance_due": float(service_balance),
            },
            "total_outstanding": float(sales_balance + service_balance),
        }

    @staticmethod
    def get_aging_report(stall=None):
        """
        Get aging report for outstanding balances.

        Buckets: Current (0-30 days), 31-60 days, 61-90 days, 90+ days
        """
        from sales.models import PaymentStatus as SalesPaymentStatus
        from sales.models import SalesTransaction
        from services.models import PaymentStatus as ServicePaymentStatus
        from services.models import Service

        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)
        sixty_days_ago = today - timedelta(days=60)
        ninety_days_ago = today - timedelta(days=90)

        # Sales aging (exclude service-linked transactions to avoid double-counting)
        sales_qs = SalesTransaction.objects.filter(
            is_deleted=False,
            voided=False,
            payment_status__in=[SalesPaymentStatus.UNPAID, SalesPaymentStatus.PARTIAL],
        ).exclude(transaction_type='service')
        if stall:
            sales_qs = sales_qs.filter(stall=stall)

        sales_aging = sales_qs.aggregate(
            current=Sum(
                Case(
                    When(
                        created_at__date__gte=thirty_days_ago,
                        then=F("items__quantity") * F("items__final_price_per_unit") - Coalesce(F("payments__amount"), Value(0))
                    ),
                    default=Value(0),
                )
            ),
            days_31_60=Sum(
                Case(
                    When(
                        created_at__date__gte=sixty_days_ago,
                        created_at__date__lt=thirty_days_ago,
                        then=F("items__quantity") * F("items__final_price_per_unit") - Coalesce(F("payments__amount"), Value(0))
                    ),
                    default=Value(0),
                )
            ),
            days_61_90=Sum(
                Case(
                    When(
                        created_at__date__gte=ninety_days_ago,
                        created_at__date__lt=sixty_days_ago,
                        then=F("items__quantity") * F("items__final_price_per_unit") - Coalesce(F("payments__amount"), Value(0))
                    ),
                    default=Value(0),
                )
            ),
            days_90_plus=Sum(
                Case(
                    When(
                        created_at__date__lt=ninety_days_ago,
                        then=F("items__quantity") * F("items__final_price_per_unit") - Coalesce(F("payments__amount"), Value(0))
                    ),
                    default=Value(0),
                )
            ),
        )

        # Service aging
        service_qs = Service.objects.filter(
            is_deleted=False,
            payment_status__in=[ServicePaymentStatus.UNPAID, ServicePaymentStatus.PARTIAL],
        ).exclude(status='cancelled')
        if stall:
            service_qs = service_qs.filter(stall=stall)

        service_aging = service_qs.aggregate(
            current=Sum(
                Case(
                    When(
                        created_at__date__gte=thirty_days_ago,
                        then=F("total_revenue") - Coalesce(F("payments__amount"), Value(0))
                    ),
                    default=Value(0),
                )
            ),
            days_31_60=Sum(
                Case(
                    When(
                        created_at__date__gte=sixty_days_ago,
                        created_at__date__lt=thirty_days_ago,
                        then=F("total_revenue") - Coalesce(F("payments__amount"), Value(0))
                    ),
                    default=Value(0),
                )
            ),
            days_61_90=Sum(
                Case(
                    When(
                        created_at__date__gte=ninety_days_ago,
                        created_at__date__lt=sixty_days_ago,
                        then=F("total_revenue") - Coalesce(F("payments__amount"), Value(0))
                    ),
                    default=Value(0),
                )
            ),
            days_90_plus=Sum(
                Case(
                    When(
                        created_at__date__lt=ninety_days_ago,
                        then=F("total_revenue") - Coalesce(F("payments__amount"), Value(0))
                    ),
                    default=Value(0),
                )
            ),
        )

        return {
            "sales": {
                "current": float(sales_aging["current"] or 0),
                "days_31_60": float(sales_aging["days_31_60"] or 0),
                "days_61_90": float(sales_aging["days_61_90"] or 0),
                "days_90_plus": float(sales_aging["days_90_plus"] or 0),
            },
            "services": {
                "current": float(service_aging["current"] or 0),
                "days_31_60": float(service_aging["days_31_60"] or 0),
                "days_61_90": float(service_aging["days_61_90"] or 0),
                "days_90_plus": float(service_aging["days_90_plus"] or 0),
            },
            "total": {
                "current": float((sales_aging["current"] or 0) + (service_aging["current"] or 0)),
                "days_31_60": float((sales_aging["days_31_60"] or 0) + (service_aging["days_31_60"] or 0)),
                "days_61_90": float((sales_aging["days_61_90"] or 0) + (service_aging["days_61_90"] or 0)),
                "days_90_plus": float((sales_aging["days_90_plus"] or 0) + (service_aging["days_90_plus"] or 0)),
            },
        }


# ----------------------------------
# Service Analytics
# ----------------------------------
class ServiceAnalytics:
    """Analytics for service operations."""

    @staticmethod
    def get_service_summary(start_date=None, end_date=None, stall=None):
        """Get service performance summary."""
        from services.models import Service
        from utils.enums import ServiceStatus

        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()

        qs = Service.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        if stall:
            qs = qs.filter(stall=stall)

        # Overall metrics
        aggregates = qs.aggregate(
            total_services=Count("id"),
            completed=Count("id", filter=Q(status=ServiceStatus.COMPLETED)),
            cancelled=Count("id", filter=Q(status=ServiceStatus.CANCELLED)),
            in_progress=Count("id", filter=Q(status=ServiceStatus.IN_PROGRESS)),
            total_revenue=Sum("total_revenue"),
            avg_revenue=Avg("total_revenue"),
        )

        # By service type
        by_type = qs.values("service_type").annotate(
            count=Count("id"),
            revenue=Sum("total_revenue"),
        ).order_by("-count")

        # Completion rate
        total = aggregates["total_services"] or 0
        completed = aggregates["completed"] or 0
        completion_rate = (completed / total * 100) if total > 0 else 0

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_services": total,
            "completed": completed,
            "cancelled": aggregates["cancelled"] or 0,
            "in_progress": aggregates["in_progress"] or 0,
            "completion_rate": float(completion_rate),
            "total_revenue": float(aggregates["total_revenue"] or 0),
            "average_revenue": float(aggregates["avg_revenue"] or 0),
            "by_type": [
                {
                    "service_type": item["service_type"],
                    "count": item["count"],
                    "revenue": float(item["revenue"] or 0),
                }
                for item in by_type
            ],
        }

    @staticmethod
    def get_technician_productivity(start_date=None, end_date=None):
        """Get technician productivity report."""
        from services.models import TechnicianAssignment
        from utils.enums import ServiceStatus

        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()

        # Get assignments in date range
        assignments = TechnicianAssignment.objects.filter(
            service__created_at__date__gte=start_date,
            service__created_at__date__lte=end_date,
        ).select_related("technician", "service")

        # Group by technician
        tech_data = {}
        for assignment in assignments:
            tech_id = assignment.technician.id
            tech_name = assignment.technician.get_full_name()

            if tech_id not in tech_data:
                tech_data[tech_id] = {
                    "technician_id": tech_id,
                    "technician_name": tech_name,
                    "total_assignments": 0,
                    "completed": 0,
                    "in_progress": 0,
                    "total_revenue": Decimal("0"),
                }

            tech_data[tech_id]["total_assignments"] += 1
            if assignment.service.status == ServiceStatus.COMPLETED:
                tech_data[tech_id]["completed"] += 1
                tech_data[tech_id]["total_revenue"] += assignment.service.total_revenue or Decimal("0")
            elif assignment.service.status == ServiceStatus.IN_PROGRESS:
                tech_data[tech_id]["in_progress"] += 1

        # Calculate completion rates and format
        result = []
        for data in tech_data.values():
            total = data["total_assignments"]
            completed = data["completed"]
            completion_rate = (completed / total * 100) if total > 0 else 0

            result.append({
                "technician_id": data["technician_id"],
                "technician_name": data["technician_name"],
                "total_assignments": total,
                "completed": completed,
                "in_progress": data["in_progress"],
                "completion_rate": float(completion_rate),
                "total_revenue": float(data["total_revenue"]),
                "avg_revenue_per_service": float(data["total_revenue"] / completed) if completed > 0 else 0,
            })

        return sorted(result, key=lambda x: x["total_revenue"], reverse=True)


# ----------------------------------
# Employee Performance Analytics
# ----------------------------------
class EmployeePerformanceAnalytics:
    """Analytics for employee performance including services and attendance."""

    @staticmethod
    def get_employee_performance(start_date=None, end_date=None):
        """
        Get comprehensive employee performance statistics.

        Returns:
        - top_service_types: Which service types are most completed
        - top_technicians: Employees with most service assignments
        - attendance_leaders: Most late and most early/on-time employees
        """
        from attendance.models import DailyAttendance
        from services.models import Service, TechnicianAssignment
        from users.models import CustomUser
        from utils.enums import ServiceStatus

        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()

        # ── Top Service Types (most completed) ──
        top_service_types = list(
            Service.objects.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
                status=ServiceStatus.COMPLETED,
            )
            .values("service_type")
            .annotate(
                count=Count("id"),
                revenue=Sum("total_revenue"),
            )
            .order_by("-count")[:6]
        )
        top_service_types = [
            {
                "service_type": item["service_type"],
                "count": item["count"],
                "revenue": float(item["revenue"] or 0),
            }
            for item in top_service_types
        ]

        # ── Top Technicians by Assignments ──
        assignments = (
            TechnicianAssignment.objects.filter(
                service__created_at__date__gte=start_date,
                service__created_at__date__lte=end_date,
                technician__is_deleted=False,
            )
            .values("technician__id", "technician__first_name", "technician__last_name")
            .annotate(
                total_assignments=Count("id"),
                completed=Count(
                    "id",
                    filter=Q(service__status=ServiceStatus.COMPLETED),
                ),
                total_revenue=Coalesce(
                    Sum(
                        "service__total_revenue",
                        filter=Q(service__status=ServiceStatus.COMPLETED),
                    ),
                    Value(0, output_field=DecimalField()),
                    output_field=DecimalField(),
                ),
            )
            .order_by("-total_assignments")[:10]
        )

        top_technicians = []
        for a in assignments:
            total = a["total_assignments"] or 0
            completed = a["completed"] or 0
            name = f"{a['technician__first_name']} {a['technician__last_name']}".strip()
            top_technicians.append({
                "employee_id": a["technician__id"],
                "employee_name": name or "Unknown",
                "total_assignments": total,
                "completed": completed,
                "completion_rate": round((completed / total * 100) if total > 0 else 0, 1),
                "total_revenue": float(a["total_revenue"] or 0),
            })

        # ── Attendance Stats ──
        attendance_qs = DailyAttendance.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            status="APPROVED",
            is_deleted=False,
            employee__is_deleted=False,
            employee__include_in_payroll=True,
        ).exclude(attendance_type__in=["ABSENT", "LEAVE", "INVALID"])

        # Most late employees
        late_stats = list(
            attendance_qs.filter(is_late=True)
            .values("employee__id", "employee__first_name", "employee__last_name")
            .annotate(
                late_count=Count("id"),
                total_late_minutes=Sum("late_minutes"),
            )
            .order_by("-late_count")[:5]
        )
        most_late = [
            {
                "employee_id": item["employee__id"],
                "employee_name": f"{item['employee__first_name']} {item['employee__last_name']}".strip() or "Unknown",
                "late_count": item["late_count"],
                "total_late_minutes": item["total_late_minutes"] or 0,
            }
            for item in late_stats
        ]

        # Most punctual employees (days present & not late)
        punctual_stats = list(
            attendance_qs.values("employee__id", "employee__first_name", "employee__last_name")
            .annotate(
                total_days=Count("id"),
                on_time_days=Count("id", filter=Q(is_late=False)),
                late_days=Count("id", filter=Q(is_late=True)),
                total_paid_hours=Sum("paid_hours"),
                full_days=Count("id", filter=Q(attendance_type="FULL_DAY")),
            )
            .order_by("-on_time_days")[:5]
        )
        most_punctual = [
            {
                "employee_id": item["employee__id"],
                "employee_name": f"{item['employee__first_name']} {item['employee__last_name']}".strip() or "Unknown",
                "total_days": item["total_days"],
                "on_time_days": item["on_time_days"],
                "late_days": item["late_days"],
                "punctuality_rate": round(
                    (item["on_time_days"] / item["total_days"] * 100) if item["total_days"] > 0 else 0, 1
                ),
                "total_paid_hours": float(item["total_paid_hours"] or 0),
                "full_days": item["full_days"],
            }
            for item in punctual_stats
        ]

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "top_service_types": top_service_types,
            "top_technicians": top_technicians,
            "most_late": most_late,
            "most_punctual": most_punctual,
        }


# ----------------------------------
# Warranty Analytics
# ----------------------------------
class WarrantyAnalytics:
    """Analytics for warranty claims and costs."""

    @staticmethod
    def get_warranty_summary(start_date=None, end_date=None):
        """Get warranty claims summary."""
        try:
            from installations.models import WarrantyClaim
        except ImportError:
            return {"error": "Warranty module not available"}

        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()

        qs = WarrantyClaim.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )

        aggregates = qs.aggregate(
            total_claims=Count("id"),
            approved=Count("id", filter=Q(status="approved")),
            rejected=Count("id", filter=Q(status="rejected")),
            pending=Count("id", filter=Q(status="pending")),
            completed=Count("id", filter=Q(status="completed")),
        )

        # Get claims with services to calculate costs
        claims_with_services = qs.filter(service__isnull=False).select_related("service")

        total_cost = sum(
            claim.service.total_revenue
            for claim in claims_with_services
            if claim.service and claim.service.total_revenue
        )

        avg_cost = total_cost / len(claims_with_services) if claims_with_services else 0

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_claims": aggregates["total_claims"] or 0,
            "approved": aggregates["approved"] or 0,
            "rejected": aggregates["rejected"] or 0,
            "pending": aggregates["pending"] or 0,
            "completed": aggregates["completed"] or 0,
            "approval_rate": float((aggregates["approved"] or 0) / (aggregates["total_claims"] or 1) * 100),
            "total_warranty_cost": float(total_cost),
            "average_claim_cost": float(avg_cost),
        }


# ----------------------------------
# Client Analytics
# ----------------------------------
class ClientAnalytics:
    """Analytics for client behavior and patterns."""

    @staticmethod
    def get_top_clients(start_date=None, end_date=None, limit=10):
        """Get top clients by total spending."""
        from clients.models import Client
        from sales.models import SalesItem
        from services.models import Service

        if not start_date:
            start_date = timezone.now().date() - timedelta(days=90)
        if not end_date:
            end_date = timezone.now().date()

        # Get all clients with activity
        clients = Client.objects.all()

        client_data = []
        for client in clients:
            # Sales spending
            sales_total = SalesItem.objects.filter(
                transaction__client=client,
                transaction__created_at__date__gte=start_date,
                transaction__created_at__date__lte=end_date,
                transaction__is_deleted=False,
            ).aggregate(
                total=Sum(F("quantity") * F("final_price_per_unit"))
            )["total"] or Decimal("0")

            # Service spending
            service_total = Service.objects.filter(
                client=client,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
            ).aggregate(
                total=Sum("total_revenue")
            )["total"] or Decimal("0")

            total_spending = sales_total + service_total

            if total_spending > 0:
                client_data.append({
                    "client_id": client.id,
                    "client_name": client.full_name,
                    "contact_number": client.contact_number,
                    "sales_spending": float(sales_total),
                    "service_spending": float(service_total),
                    "total_spending": float(total_spending),
                })

        # Sort and limit
        client_data.sort(key=lambda x: x["total_spending"], reverse=True)
        return client_data[:limit]


# ----------------------------------
# Inventory Analytics
# ----------------------------------
class InventoryAnalytics:
    """Analytics for inventory turnover and stock levels."""

    @staticmethod
    def get_inventory_summary(stall=None):
        """Get inventory health summary."""
        from inventory.models import Stock

        qs = Stock.objects.filter(is_deleted=False, track_stock=True)
        if stall:
            qs = qs.filter(stall=stall)

        aggregates = qs.aggregate(
            total_items=Count("id"),
            total_value=Sum(F("quantity") * F("item__price")),
            out_of_stock=Count("id", filter=Q(quantity=0)),
            low_stock=Count("id", filter=Q(quantity__gt=0, quantity__lte=F("low_stock_threshold"))),
        )

        return {
            "total_items": aggregates["total_items"] or 0,
            "total_value": float(aggregates["total_value"] or 0),
            "out_of_stock": aggregates["out_of_stock"] or 0,
            "low_stock": aggregates["low_stock"] or 0,
            "healthy_stock": (aggregates["total_items"] or 0) - (aggregates["out_of_stock"] or 0) - (aggregates["low_stock"] or 0),
        }

    @staticmethod
    def get_stock_turnover(start_date=None, end_date=None, limit=20):
        """Get stock turnover analysis."""
        from inventory.models import Item, Stock
        from sales.models import SalesItem
        from services.models import ApplianceItemUsed

        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()

        # Sales quantities
        sales_data = SalesItem.objects.filter(
            transaction__created_at__date__gte=start_date,
            transaction__created_at__date__lte=end_date,
            transaction__is_deleted=False,
        ).values("item").annotate(
            quantity_sold=Sum("quantity"),
        )

        # Service usage quantities
        service_data = ApplianceItemUsed.objects.filter(
            appliance__service__created_at__date__gte=start_date,
            appliance__service__created_at__date__lte=end_date,
        ).values("item").annotate(
            quantity_used=Sum("quantity"),
        )

        # Combine data
        item_usage = {}
        for item in sales_data:
            item_id = item["item"]
            item_usage.setdefault(item_id, 0)
            item_usage[item_id] += item["quantity_sold"]

        for item in service_data:
            item_id = item["item"]
            item_usage.setdefault(item_id, 0)
            item_usage[item_id] += item["quantity_used"]

        # Get item details
        result = []
        for item_id, quantity in item_usage.items():
            try:
                item = Item.objects.get(id=item_id)
                result.append({
                    "item_id": item.id,
                    "item_name": item.name,
                    "quantity_moved": quantity,
                    "current_stock": Stock.objects.filter(item=item, is_deleted=False).aggregate(
                        total=Sum("quantity")
                    )["total"] or 0,
                })
            except Item.DoesNotExist:
                continue

        # Sort by quantity moved
        result.sort(key=lambda x: x["quantity_moved"], reverse=True)
        return result[:limit]


# ----------------------------------
# Consolidated Dashboard
# ----------------------------------
class DashboardAnalytics:
    """Consolidated analytics for dashboard views."""

    @staticmethod
    def get_dashboard_summary(start_date=None, end_date=None, stall=None):
        """Get comprehensive dashboard summary."""
        if not start_date:
            start_date = timezone.now().date() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now().date()

        return {
            "revenue": RevenueAnalytics.get_revenue_summary(start_date, end_date, stall),
            "collections": PaymentAnalytics.get_collection_summary(start_date, end_date, stall),
            "outstanding": OutstandingAnalytics.get_outstanding_summary(stall),
            "services": ServiceAnalytics.get_service_summary(start_date, end_date, stall),
            "inventory": InventoryAnalytics.get_inventory_summary(stall),
        }


# ----------------------------------
# Helper Functions
# ----------------------------------
def get_date_range_from_request(request):
    """Extract date range from request query parameters."""
    from django.utils.dateparse import parse_date

    start_param = request.query_params.get("start_date")
    end_param = request.query_params.get("end_date")

    start_date = parse_date(start_param) if start_param else timezone.now().date() - timedelta(days=30)
    end_date = parse_date(end_param) if end_param else timezone.now().date()

    return start_date, end_date


def get_stall_from_request(request):
    """Extract stall filter from request."""
    from inventory.models import Stall

    stall_id = request.query_params.get("stall")
    if stall_id:
        try:
            return Stall.objects.get(id=stall_id)
        except Stall.DoesNotExist:
            return None
    return None
