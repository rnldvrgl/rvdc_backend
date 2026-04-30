from django.core.cache import cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from quotations.models import (
    Quotation,
    QuotationPriceListTemplate,
    QuotationTermsTemplate,
)
from utils.soft_delete import SoftDeleteViewSetMixin

from .serializers import (
    QuotationPriceListTemplateSerializer,
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


class QuotationPriceListTemplateViewSet(viewsets.ModelViewSet):
    queryset = QuotationPriceListTemplate.objects.prefetch_related("aircon_models").filter(is_active=True)
    serializer_class = QuotationPriceListTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["name", "description", "aircon_models__name", "aircon_models__brand__name"]
    filterset_fields = ["is_default"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-is_default", "name"]
    pagination_class = None


class QuotationViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    queryset = Quotation.objects.select_related(
        "client",
        "created_by",
        "stall",
        "price_list_template",
    ).prefetch_related("items", "payments", "price_list_template__aircon_models")
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

    def create(self, request, *args, **kwargs):
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            import hashlib, json
            body_hash = hashlib.sha256(
                json.dumps(request.data, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            idempotency_key = f"{request.user.id}:{body_hash}"

        cache_key = f"quotation_create_idempotency:{idempotency_key}"

        if cache.get(cache_key):
            return Response(
                {"detail": "Duplicate request detected. This quotation was already submitted."},
                status=status.HTTP_409_CONFLICT,
            )

        cache.set(cache_key, True, timeout=30)

        try:
            return super().create(request, *args, **kwargs)
        except Exception:
            cache.delete(cache_key)
            raise

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
