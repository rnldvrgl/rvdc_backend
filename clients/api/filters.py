from clients.models import Client
from django_filters import rest_framework as filters


class ClientFilter(filters.FilterSet):
    class Meta:
        model = Client
        fields = ["is_blocklisted", "is_deleted"]
