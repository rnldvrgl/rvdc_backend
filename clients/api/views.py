from rest_framework import generics, permissions, filters
from clients.models import Client
from clients.api.serializers import ClientSerializer
from django_filters.rest_framework import DjangoFilterBackend
from utils.logger import log_activity


class ClientListCreateView(generics.ListCreateAPIView):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    filterset_fields = ["full_name", "phone"]
    search_fields = ["full_name", "phone", "province", "city", "barangay", "address"]

    def perform_create(self, serializer):
        client = serializer.save()
        log_activity(
            user=self.request.user,
            instance=client,
            action="Created Client",
            note=f"Client '{client.full_name}' created.",
        )


class ClientDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_update(self, serializer):
        client = serializer.save()
        log_activity(
            user=self.request.user,
            instance=client,
            action="Updated Client",
            note=f"Client '{client.full_name}' updated.",
        )

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action="Deleted Client",
            note=f"Client '{instance.full_name}' marked as deleted.",
        )
