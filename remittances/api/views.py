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

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_remitted:
            return Response(
                {"detail": "Cannot edit a remittance that has already been marked as remitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

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
            stall=stall, remittance_date=target_date
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

        # Get expenses (normal expenses minus reimbursements)
        normal_expenses = (
            Expense.objects.filter(
                stall=stall, expense_date=target_date, is_deleted=False, is_reimbursement=False
            ).aggregate(total=Sum("paid_amount"))["total"]
            or Decimal("0")
        )
        reimbursements = (
            Expense.objects.filter(
                stall=stall, expense_date=target_date, is_deleted=False, is_reimbursement=True
            ).aggregate(total=Sum("paid_amount"))["total"]
            or Decimal("0")
        )
        total_expenses = normal_expenses - reimbursements

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

    @action(detail=True, methods=["post"], url_path="recalculate")
    def recalculate(self, request, pk=None):
        """
        Recalculate sales totals and expenses for a not-yet-remitted remittance.
        This picks up any new sales or expenses added after the remittance was created.
        POST /remittances/{id}/recalculate/
        """
        remittance = self.get_object()

        if remittance.is_remitted:
            return Response(
                {"detail": "Cannot recalculate a remittance that has already been marked as remitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stall = remittance.stall
        target_date = remittance.remittance_date

        def sum_sales(payment_type: str):
            total_payments = SalesPayment.objects.filter(
                transaction__stall=stall,
                payment_date__date=target_date,
                transaction__payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                transaction__voided=False,
                transaction__is_deleted=False,
                payment_type=payment_type,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

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

        normal_expenses = (
            Expense.objects.filter(
                stall=stall, expense_date=target_date, is_deleted=False, is_reimbursement=False
            ).aggregate(total=Sum("paid_amount"))["total"]
            or Decimal("0")
        )
        reimbursements = (
            Expense.objects.filter(
                stall=stall, expense_date=target_date, is_deleted=False, is_reimbursement=True
            ).aggregate(total=Sum("paid_amount"))["total"]
            or Decimal("0")
        )
        total_expenses = normal_expenses - reimbursements

        remittance.total_sales_cash = sales["cash"]
        remittance.total_sales_gcash = sales["gcash"]
        remittance.total_sales_credit = sales["credit"]
        remittance.total_sales_debit = sales["debit"]
        remittance.total_sales_cheque = sales["cheque"]
        remittance.total_expenses = total_expenses
        remittance.save()

        serializer = self.get_serializer(remittance)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="sub-stall-payable")
    def sub_stall_payable(self, request):
        """
        Compute sub-stall payable from services only for today.
        Shows how much the main stall owes the sub stall for parts used
        in services — excludes direct sales.
        GET /remittances/sub-stall-payable/
        """
        target_date = timezone.localdate()

        sub_stall = Stall.objects.filter(stall_type="sub", is_system=True).first()
        if not sub_stall:
            return Response(
                {"detail": "No sub stall configured."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from services.models import Service

        # Get services that have a sub stall transaction with payments today
        services_with_parts = (
            Service.objects.filter(
                related_sub_transaction__isnull=False,
                related_sub_transaction__stall=sub_stall,
                related_sub_transaction__payments__payment_date__date=target_date,
                related_sub_transaction__voided=False,
                related_sub_transaction__is_deleted=False,
            )
            .select_related("client", "related_sub_transaction")
            .distinct()
        )

        # Get sub stall transaction IDs that are service-linked
        service_sub_tx_ids = services_with_parts.values_list(
            "related_sub_transaction_id", flat=True
        )

        def sum_service_sub_sales(payment_type: str):
            from sales.models import SalesTransaction

            total = SalesPayment.objects.filter(
                transaction_id__in=service_sub_tx_ids,
                payment_date__date=target_date,
                transaction__payment_status__in=[
                    PaymentStatus.PAID, PaymentStatus.PARTIAL,
                ],
                payment_type=payment_type,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

            if payment_type == "cash":
                total_change = SalesTransaction.objects.filter(
                    id__in=service_sub_tx_ids,
                    payment_status__in=[
                        PaymentStatus.PAID, PaymentStatus.PARTIAL,
                    ],
                    payments__payment_date__date=target_date,
                ).distinct().aggregate(
                    total=Sum("change_amount")
                )["total"] or Decimal("0")
                return total - total_change

            return total

        sales = {
            pt: sum_service_sub_sales(pt)
            for pt in ["cash", "gcash", "credit", "debit", "cheque"]
        }
        total = sum(sales.values())
        e_payments = (
            sales["gcash"] + sales["credit"] + sales["debit"] + sales["cheque"]
        )

        # Only cash is payable — e-payments go directly to admin
        cash_payable = max(Decimal("0"), sales["cash"])

        # Services breakdown
        services_list = []
        for svc in services_with_parts:
            client_name = ""
            if svc.client:
                client_name = svc.client.name if hasattr(svc.client, "name") else str(svc.client)
            sub_tx = svc.related_sub_transaction
            tx_total = Decimal("0")
            if sub_tx:
                tx_total = (
                    SalesPayment.objects.filter(
                        transaction=sub_tx,
                        payment_date__date=target_date,
                    ).aggregate(total=Sum("amount"))["total"]
                    or Decimal("0")
                )
            services_list.append({
                "service_id": svc.id,
                "client_name": client_name,
                "sub_stall_revenue": str(svc.sub_stall_revenue),
                "paid_today": str(tx_total),
            })

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
            "cash_payable": str(cash_payable),
            "services": services_list,
        })
