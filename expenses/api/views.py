from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import F, Sum
from expenses.models import Expense
from .serializers import ExpenseSerializer, ExpensePaymentSerializer
from django.utils import timezone


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all().order_by("-created_at")
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ["description", "stall__name"]
    filterset_fields = ["stall", "created_by", "source"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, source="manual")

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
