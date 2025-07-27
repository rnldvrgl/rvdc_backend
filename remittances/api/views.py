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
