from django.db.models import F, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from expenses.api.filters import ExpenseFilter
from expenses.models import Expense
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.filters.options import get_stall_options
from utils.filters.role_filters import get_role_based_filter_response
from utils.query import get_role_filtered_queryset

from .serializers import ExpensePaymentSerializer, ExpenseSerializer


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all().order_by("-created_at")
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ExpenseFilter
    search_fields = ["description", "stall__name"]
    ordering_fields = [
        "created_at",
        "updated_at",
        "total_price",
        "paid_amount",
        "paid_at",
        "description",
    ]
    ordering = ["-created_at"]

    def get_queryset(self):
        return get_role_filtered_queryset(self.request, super().get_queryset())

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "stall": {
                "options": get_stall_options,
                "exclude_for": ["clerk", "manager"],
            },
            "source": {
                "options": lambda: [
                    {"label": "Manual", "value": "manual"},
                    {"label": "Stock Transfer", "value": "transfer"},
                ]
            },
            "is_paid": {
                "options": lambda: [
                    {"label": "Paid", "value": "true"},
                    {"label": "Unpaid", "value": "false"},
                ],
            },
        }

        ordering_config = [
            {"label": "Created At", "value": "created_at"},
            {"label": "Paid At", "value": "paid_at"},
            {"label": "Total Price", "value": "total_price"},
            {"label": "Paid Amount", "value": "paid_amount"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)

    def perform_create(self, serializer):
        user = self.request.user
        stall = serializer.validated_data.get("stall", None)

        # Only admin can create stock room expenses (stall=None)
        if stall is None and user.role != "admin":
            raise PermissionDenied("Only admins can add stock room expenses.")

        instance = serializer.save(
            created_by=user,
            source="manual",
            is_paid=True,
            paid_at=timezone.now(),
        )
        instance.paid_amount = instance.total_price
        instance.save()

    @action(detail=False, methods=["get"], url_path="unpaid-total")
    def unpaid_total(self, request):
        stall_id = request.query_params.get("stall")
        if not stall_id:
            return Response({"error": "Please provide ?stall=id"}, status=400)
        unpaid = (
            Expense.objects.filter(
                stall_id=stall_id, paid_amount__lt=F("total_price")
            ).aggregate(total=Sum(F("total_price") - F("paid_amount")))["total"]
            or 0
        )
        return Response({"stall": stall_id, "unpaid_total": unpaid})

    @action(detail=True, methods=["patch"], url_path="pay")
    def pay(self, request, pk=None):
        expense = self.get_object()
        serializer = ExpensePaymentSerializer(expense, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="mark-as-paid")
    def mark_as_paid(self, request, pk=None):
        expense = self.get_object()
        if expense.is_paid:
            return Response({"detail": "Expense already marked as paid."}, status=400)

        expense.paid_amount = expense.total_price
        expense.paid_at = timezone.now()
        expense.is_paid = True
        expense.save()

        serializer = self.get_serializer(expense)
        return Response(serializer.data)
