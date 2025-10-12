from rest_framework import viewsets, permissions, filters, serializers
from clients.models import Client
from clients.api.serializers import ClientSerializer
from django_filters.rest_framework import DjangoFilterBackend
from utils.filters.role_filters import get_role_based_filter_response
from utils.query import filter_by_date_range
from clients.api.filters import ClientFilter
from rest_framework.decorators import action
from rest_framework.response import Response


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ClientFilter
    search_fields = [
        "full_name",
        "contact_number",
        "province",
        "city",
        "barangay",
        "address",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        # Apply role/date-based filtering
        qs = super().get_queryset()
        return filter_by_date_range(self.request, qs)

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "is_blocklisted": {
                "options": lambda: [
                    {"label": "Blocklisted", "value": "true"},
                    {"label": "Not Blocklisted", "value": "false"},
                ],
            },
            "is_deleted": {
                "options": lambda: [
                    {"label": "Deleted", "value": "true"},
                    {"label": "Not Deleted", "value": "false"},
                ],
            },
            "province": {
                "options": lambda: Client.objects.values_list("province", flat=True)
                .distinct()
                .order_by("province"),
            },
            "city": {
                "options": lambda: Client.objects.values_list("city", flat=True)
                .distinct()
                .order_by("city"),
            },
        }
        ordering_config = [
            {"label": "Full Name", "value": "full_name"},
            {"label": "Created Date", "value": "created_at"},
            {"label": "City", "value": "city"},
            {"label": "Province", "value": "province"},
        ]
        return get_role_based_filter_response(request, filters_config, ordering_config)

    def perform_create(self, serializer):
        full_name = serializer.validated_data.get("full_name")
        contact_number = serializer.validated_data.get("contact_number") or None

        if Client.objects.filter(
            full_name=full_name, contact_number=contact_number
        ).exists():
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "A client with this full name and contact number already exists."
                    ]
                }
            )

        if (
            contact_number
            and Client.objects.filter(contact_number=contact_number).exists()
        ):
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "A client with this contact number already exists."
                    ]
                }
            )

        serializer.save(contact_number=contact_number)
