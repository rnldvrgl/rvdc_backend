from rest_framework import viewsets, permissions
from remittances.models import RemittanceRecord
from remittances.api.serializers import RemittanceRecordSerializer
from utils.query import get_role_filtered_queryset
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone


class RemittanceRecordViewSet(viewsets.ModelViewSet):
    queryset = RemittanceRecord.objects.select_related(
        "stall", "remitted_by"
    ).prefetch_related("cash_breakdown")
    serializer_class = RemittanceRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = get_role_filtered_queryset(self.request, super().get_queryset())

        stall_id = self.request.query_params.get("stall")
        if stall_id and self.request.user.role == "admin":
            qs = qs.filter(stall_id=stall_id)

        return qs

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def mark_remitted(self, request, pk=None):
        remittance = self.get_object()

        if remittance.is_remitted:
            return Response(
                {"detail": "Already marked as remitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        remittance.is_remitted = True
        remittance.remitted_at = timezone.now()
        remittance.save()

        return Response({"detail": "Remittance marked as remitted."})
