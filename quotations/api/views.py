from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated

from quotations.models import Quotation, QuotationTermsTemplate
from utils.soft_delete import SoftDeleteViewSetMixin

from .serializers import (
    QuotationListSerializer,
    QuotationSerializer,
    QuotationTermsTemplateSerializer,
)


class QuotationTermsTemplateViewSet(viewsets.ModelViewSet):
    queryset = QuotationTermsTemplate.objects.filter(is_active=True)
    serializer_class = QuotationTermsTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["name"]
    filterset_fields = ["category", "is_default"]
    ordering_fields = ["name", "created_at"]
    ordering = ["category", "name"]
    pagination_class = None  # Return all templates without pagination


class QuotationViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    queryset = Quotation.objects.select_related("client", "created_by").prefetch_related("items")
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = [
        "client_name",
        "project_description",
        "items__description",
    ]
    filterset_fields = ["status"]
    ordering_fields = ["quote_date", "created_at", "total", "valid_until"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return QuotationListSerializer
        return QuotationSerializer

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
