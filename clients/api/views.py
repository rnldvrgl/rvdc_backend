from rest_framework import generics, permissions, filters
from clients.models import Client
from clients.api.serializers import ClientSerializer
from django_filters.rest_framework import DjangoFilterBackend
from utils.mixins import LogCreateMixin, LogUpdateMixin, LogSoftDeleteMixin


class ClientListCreateView(LogCreateMixin, generics.ListCreateAPIView):
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
