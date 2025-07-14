from rest_framework import generics, permissions

from inventory.models import Item, Stall, ProductCategory
from inventory.api.serializers import (
    ItemSerializer,
    StallSerializer,
    ProductCategorySerializer,
)
from clients.api.serializers import ClientSerializer
from clients.models import Client
from users.models import CustomUser
from users.api.serializers import TechnicianSerializer


class BaseChoicesAPIView(generics.ListAPIView):
    pagination_class = None
    permission_classes = [permissions.IsAuthenticated]


class ItemChoicesAPIView(BaseChoicesAPIView):
    queryset = Item.objects.filter(is_deleted=False)
    serializer_class = ItemSerializer


class StallChoicesAPIView(BaseChoicesAPIView):
    serializer_class = StallSerializer

    def get_queryset(self):
        queryset = Stall.objects.filter(is_deleted=False)
        exclude_id = self.request.query_params.get("exclude")
        if exclude_id:
            queryset = queryset.exclude(id=exclude_id)
        return queryset


class ProductCategoryChoicesAPIView(BaseChoicesAPIView):
    queryset = ProductCategory.objects.filter(is_deleted=False)
    serializer_class = ProductCategorySerializer


class ClientChoicesAPIView(BaseChoicesAPIView):
    queryset = Client.objects.filter(is_deleted=False)
    serializer_class = ClientSerializer


class TechnicianChoicesAPIView(BaseChoicesAPIView):
    queryset = CustomUser.objects.filter(role="technician", is_deleted=False)
    serializer_class = TechnicianSerializer
