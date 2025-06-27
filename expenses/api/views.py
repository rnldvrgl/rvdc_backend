from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from .serializers import ExpenseSerializer
from expenses.models import Expense
from django_filters.rest_framework import DjangoFilterBackend


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all().order_by("-created_at")
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ["description", "stall__name"]
    filterset_fields = ["stall", "created_by", "source"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, source="manual")
