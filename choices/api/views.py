from rest_framework import generics, permissions

from inventory.models import Item, Stall, ProductCategory
from inventory.api.serializers import (
    ItemSerializer,
    StallSerializer,
    ProductCategorySerializer,
)
from clients.api.serializers import ClientSerializer
from clients.models import Client
from installations.api.serializers import AirconBrandSerializer
from installations.models import AirconBrand
from users.models import CustomUser
from users.api.serializers import EmployeesSerializer, UserSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from utils.enums import AirconType, BankChoices


class ChoicesAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    choices_class = None

    def get(self, request, *args, **kwargs):
        if not self.choices_class:
            return Response({"error": "No choices_class defined."}, status=400)

        data = [
            {"value": choice.value, "label": choice.label}
            for choice in self.choices_class
        ]
        return Response(data)


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


class EmployeesChoicesAPIView(BaseChoicesAPIView):
    queryset = CustomUser.objects.exclude(role="admin").filter(is_deleted=False)
    serializer_class = EmployeesSerializer


class TechniciansChoicesAPIView(BaseChoicesAPIView):
    queryset = CustomUser.objects.filter(role="technician", is_deleted=False)
    serializer_class = UserSerializer


class BanksChoicesAPIView(ChoicesAPIView):
    choices_class = BankChoices


class AirconTypesChoicesAPIView(ChoicesAPIView):
    choices_class = AirconType


class AirconBrandsChoicesAPIView(BaseChoicesAPIView):
    queryset = AirconBrand.objects.all()
    serializer_class = AirconBrandSerializer
