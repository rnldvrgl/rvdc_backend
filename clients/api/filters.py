from django.db import models
from django_filters import rest_framework as filters
from clients.models import Client


class ClientFilter(filters.FilterSet):
    class Meta:
        model = Client
        fields = ["is_blocklisted", "is_deleted"]
