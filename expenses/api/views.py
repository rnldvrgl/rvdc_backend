from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .serializers import ExpenseSerializer
from expenses.models import Expense


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all().order_by("-created_at")
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, source="manual")
