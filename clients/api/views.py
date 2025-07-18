from rest_framework import generics, permissions, filters, serializers
from clients.models import Client
from clients.api.serializers import ClientSerializer
from django_filters.rest_framework import DjangoFilterBackend
from utils.query import filter_by_date_range
from utils.mixins import LogCreateMixin, LogUpdateMixin, LogSoftDeleteMixin


class ClientListCreateView(LogCreateMixin, generics.ListCreateAPIView):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["full_name", "contact_number"]
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
        return filter_by_date_range(self.request, super().get_queryset())

    def perform_create(self, serializer):
        full_name = serializer.validated_data.get("full_name")
        contact_number = serializer.validated_data.get("contact_number")

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

        if Client.objects.filter(contact_number=contact_number).exists():
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "A client with this contact number already exists."
                    ]
                }
            )

        serializer.save()


class ClientDetailView(
    LogUpdateMixin, LogSoftDeleteMixin, generics.RetrieveUpdateDestroyAPIView
):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["full_name", "contact_number"]
    search_fields = [
        "full_name",
        "contact_number",
        "province",
        "city",
        "barangay",
        "address",
    ]
