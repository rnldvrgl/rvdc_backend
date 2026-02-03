from clients.api.serializers import ClientSerializer
from clients.models import Client
from expenses.api.serializers import ExpenseCategoryListSerializer
from expenses.models import ExpenseCategory
from installations.api.serializers import AirconBrandSerializer
from installations.models import AirconBrand
from inventory.api.serializers import (
    ItemSerializer,
    ProductCategorySerializer,
    StallSerializer,
)
from inventory.models import Item, ProductCategory, Stall
from rest_framework import generics, permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from services.models import ApplianceType
from users.api.serializers import EmployeesSerializer, UserSerializer
from users.models import CustomUser
from utils.enums import AirconType, BankChoices


class ApplianceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplianceType
        fields = ["id", "name"]


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
        # Only return system stalls (the two main stalls: Main and Sub)
        queryset = Stall.objects.filter(is_deleted=False, is_system=True)
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


class UsersChoicesAPIView(BaseChoicesAPIView):
    queryset = CustomUser.objects.filter(is_deleted=False)
    serializer_class = UserSerializer


class BanksChoicesAPIView(ChoicesAPIView):
    choices_class = BankChoices


class AirconTypesChoicesAPIView(ChoicesAPIView):
    choices_class = AirconType


class AirconBrandsChoicesAPIView(BaseChoicesAPIView):
    queryset = AirconBrand.objects.all()
    serializer_class = AirconBrandSerializer


class ExpenseCategoriesChoicesAPIView(BaseChoicesAPIView):
    queryset = ExpenseCategory.objects.filter(is_deleted=False, is_active=True)
    serializer_class = ExpenseCategoryListSerializer


class ApplianceTypesChoicesAPIView(BaseChoicesAPIView):
    queryset = ApplianceType.objects.all()
    serializer_class = ApplianceTypeSerializer
