from rest_framework import viewsets, permissions, filters
from remittances.models import RemittanceRecord
from remittances.api.serializers import RemittanceRecordSerializer
from utils.query import get_role_filtered_queryset
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django_filters.rest_framework import DjangoFilterBackend
from remittances.api.filters import RemittanceRecordFilter
from utils.filters.options import get_stall_options
from utils.filters.role_filters import get_role_based_filter_response

from decimal import Decimal
from datetime import date
from django.db.models import Sum
from django.utils import timezone
from inventory.models import Stall
from sales.models import SalesPayment, PaymentStatus
from expenses.models import Expense


class RemittanceRecordViewSet(viewsets.ModelViewSet):
    queryset = RemittanceRecord.objects.select_related(
        "stall", "remitted_by"
    ).prefetch_related("cash_breakdown")
    serializer_class = RemittanceRecordSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = RemittanceRecordFilter
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = get_role_filtered_queryset(self.request, super().get_queryset())

        qs = qs.select_related("cash_breakdown")

        stall_id = self.request.query_params.get("stall")
        if stall_id and self.request.user.role == "admin":
            qs = qs.filter(stall_id=stall_id)

        return qs

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "stall": {
                "options": get_stall_options,
                "exclude_for": ["clerk", "manager"],
            },
            "is_remitted": {
                "options": lambda: [
                    {"label": "Remitted", "value": "true"},
                    {"label": "Not Remitted", "value": "false"},
                ]
            },
        }

        ordering_config = [
            {"label": "Date", "value": "created_at"},
            {
                "label": "Stall",
                "value": "stall__name",
                "exclude_for": ["clerk", "manager"],
            },
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)

    @action(detail=False, methods=["get"], url_path="preview")
    def preview(self, request):
        """
        Preview sales, expenses, and expected remittance for a stall + date.
        GET /remittances/preview/?stall=<id>&date=<YYYY-MM-DD>
        """
        stall_id = request.query_params.get("stall")
        date_str = request.query_params.get("date")

        if not stall_id:
            return Response(
                {"detail": "stall parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            stall = Stall.objects.get(pk=stall_id)
        except Stall.DoesNotExist:
            return Response(
                {"detail": "Stall not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Parse date or use today
        if date_str:
            try:
                target_date = date.fromisoformat(date_str)
            except ValueError:
                return Response(
                    {"detail": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target_date = timezone.localdate()

        # Check if remittance already exists for this stall + date
        already_exists = RemittanceRecord.objects.filter(
            stall=stall, created_at__date=target_date
        ).exists()

        # Compute sales by payment type
        def sum_sales(payment_type: str):
            # Sum all payments of this type for paid/partial transactions on this date
            total_payments = SalesPayment.objects.filter(
                transaction__stall=stall,
                payment_date__date=target_date,
                transaction__payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                transaction__voided=False,
                transaction__is_deleted=False,
                payment_type=payment_type,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

            # Change is always given in cash, so only subtract from cash totals.
            # Subtract once per transaction (not per payment) to avoid double-counting.
            if payment_type == "cash":
                from sales.models import SalesTransaction
                total_change = SalesTransaction.objects.filter(
                    stall=stall,
                    payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                    voided=False,
                    is_deleted=False,
                    payments__payment_date__date=target_date,
                ).distinct().aggregate(
                    total=Sum("change_amount")
                )["total"] or Decimal("0")
                return total_payments - total_change

            return total_payments

        sales = {pt: sum_sales(pt) for pt in ["cash", "gcash", "credit", "debit", "cheque"]}

        # Get expenses
        total_expenses = (
            Expense.objects.filter(
                stall=stall, created_at__date=target_date
            ).aggregate(total=Sum("paid_amount"))["total"]
            or Decimal("0")
        )

        # COD from previous day (relative to the target date, not today)
        cod_info = RemittanceRecord.get_cod_for_date(stall, target_date)
        cod_amount = Decimal(str(cod_info.get("cod_amount", 0) or 0))

        # Expected remittance
        cash_sales = sales["cash"]
        expected = max(Decimal("0"), cash_sales + cod_amount - total_expenses)

        total_collected = sum(sales.values())

        return Response({
            "date": str(target_date),
            "stall_id": stall.id,
            "stall_name": stall.name,
            "already_exists": already_exists,
            "total_sales_cash": str(sales["cash"]),
            "total_sales_gcash": str(sales["gcash"]),
            "total_sales_credit": str(sales["credit"]),
            "total_sales_debit": str(sales["debit"]),
            "total_sales_cheque": str(sales["cheque"]),
            "total_collected": str(total_collected),
            "total_expenses": str(total_expenses),
            "cod_from_previous": str(cod_amount),
            "expected_remittance": str(expected),
        })

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def mark_remitted(self, request, pk=None):
        remittance = self.get_object()

        if remittance.is_remitted:
            return Response(
                {"detail": "Already marked as remitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        remittance.is_remitted = True
        remittance.save()

        return Response({"detail": "Remittance marked as remitted."})

    @action(detail=False, methods=["get"], url_path="sub-stall-payable")
    def sub_stall_payable(self, request):
        """
        Compute total sub-stall sales for a given date.
        The main stall owes this amount to the sub stall at end-of-day settlement.
        GET /remittances/sub-stall-payable/?date=YYYY-MM-DD
        """
        date_str = request.query_params.get("date")

        if date_str:
            try:
                target_date = date.fromisoformat(date_str)
            except ValueError:
                return Response(
                    {"detail": "Invalid date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            target_date = timezone.localdate()

        sub_stall = Stall.objects.filter(stall_type="sub", is_system=True).first()
        if not sub_stall:
            return Response(
                {"detail": "No sub stall configured."},
                status=status.HTTP_404_NOT_FOUND,
            )

        def sum_sub_sales(payment_type: str):
            from sales.models import SalesTransaction
            total = SalesPayment.objects.filter(
                transaction__stall=sub_stall,
                payment_date__date=target_date,
                transaction__payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                transaction__voided=False,
                transaction__is_deleted=False,
                payment_type=payment_type,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

            if payment_type == "cash":
                total_change = SalesTransaction.objects.filter(
                    stall=sub_stall,
                    payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                    voided=False,
                    is_deleted=False,
                    payments__payment_date__date=target_date,
                ).distinct().aggregate(
                    total=Sum("change_amount")
                )["total"] or Decimal("0")
                return total - total_change

            return total

        sales = {pt: sum_sub_sales(pt) for pt in ["cash", "gcash", "credit", "debit", "cheque"]}
        total = sum(sales.values())
        e_payments = sales["gcash"] + sales["credit"] + sales["debit"] + sales["cheque"]

        # Sub stall expenses
        total_expenses = (
            Expense.objects.filter(
                stall=sub_stall, created_at__date=target_date
            ).aggregate(total=Sum("paid_amount"))["total"]
            or Decimal("0")
        )

        # Only cash is payable — e-payments (gcash, credit, debit, cheque)
        # are received directly by admin and don't need physical settlement.
        cash_payable = max(Decimal("0"), sales["cash"] - total_expenses)

        return Response({
            "date": str(target_date),
            "sub_stall_id": sub_stall.id,
            "sub_stall_name": sub_stall.name,
            "sales_cash": str(sales["cash"]),
            "sales_gcash": str(sales["gcash"]),
            "sales_credit": str(sales["credit"]),
            "sales_debit": str(sales["debit"]),
            "sales_cheque": str(sales["cheque"]),
            "total_sales": str(total),
            "e_payments_total": str(e_payments),
            "total_expenses": str(total_expenses),
            "cash_payable": str(cash_payable),
        })
