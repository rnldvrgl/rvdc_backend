from clients.api.serializers import ClientSerializer
from clients.models import Client
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
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
from utils.enums import AirconType, BankChoices, HorsePower


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

    @method_decorator(cache_page(60 * 5))  # Cache choices for 5 minutes
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


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

    def list(self, request, *args, **kwargs):
        # Skip cache — clients change frequently (new clients added often)
        return super(BaseChoicesAPIView, self).list(request, *args, **kwargs)


class EmployeesChoicesAPIView(BaseChoicesAPIView):
    queryset = CustomUser.objects.exclude(role="admin").filter(is_deleted=False, is_active=True)
    serializer_class = EmployeesSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        include_in_payroll = self.request.query_params.get('include_in_payroll')

        if include_in_payroll is not None:
            # Convert string to boolean
            if include_in_payroll.lower() in ['true', '1', 'yes']:
                queryset = queryset.filter(include_in_payroll=True)
            elif include_in_payroll.lower() in ['false', '0', 'no']:
                queryset = queryset.filter(include_in_payroll=False)

        return queryset


class TechniciansChoicesAPIView(BaseChoicesAPIView):
    queryset = CustomUser.objects.filter(is_technician=True, is_deleted=False, is_active=True)
    serializer_class = UserSerializer


class UsersChoicesAPIView(BaseChoicesAPIView):
    queryset = CustomUser.objects.filter(is_deleted=False, is_active=True)
    serializer_class = UserSerializer


class BanksChoicesAPIView(ChoicesAPIView):
    choices_class = BankChoices


class AirconTypesChoicesAPIView(ChoicesAPIView):
    choices_class = AirconType


class HorsePowerChoicesAPIView(ChoicesAPIView):
    choices_class = HorsePower


class AirconBrandsChoicesAPIView(BaseChoicesAPIView):
    queryset = AirconBrand.objects.all()
    serializer_class = AirconBrandSerializer


class ExpenseCategoriesChoicesAPIView(BaseChoicesAPIView):
    queryset = ExpenseCategory.objects.filter(is_deleted=False, is_active=True)
    serializer_class = ExpenseCategoryListSerializer


class ApplianceTypesChoicesAPIView(BaseChoicesAPIView):
    queryset = ApplianceType.objects.all()
    serializer_class = ApplianceTypeSerializer
