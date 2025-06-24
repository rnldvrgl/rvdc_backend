from rest_framework import generics, permissions, filters
from clients.models import Client
from clients.api.serializers import ClientSerializer
from django_filters.rest_framework import DjangoFilterBackend


class ClientListCreateView(generics.ListCreateAPIView):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    filterset_fields = ["full_name", "phone"]
    search_fields = ["full_name", "phone", "province", "city", "barangay", "address"]


class ClientDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()
