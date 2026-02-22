from rest_framework import generics, permissions, filters, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from utils.query import filter_by_date_range
from users.models import CustomUser, SystemSettings, CashAdvanceMovement
from users.api.serializers import EmployeesSerializer, UserSerializer, SystemSettingsSerializer, CashAdvanceMovementSerializer
from django_filters.rest_framework import DjangoFilterBackend


# List all users (admin only)
class UserListView(generics.ListAPIView):
    queryset = CustomUser.all_objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = ["username", "contact_number", "first_name", "last_name", "role"]
    search_fields = ["username", "contact_number", "first_name", "last_name"]
    ordering_fields = "__all__"

    def get_queryset(self):
        return filter_by_date_range(self.request, super().get_queryset())


# Admin: view, update, or soft delete any specific user
class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = CustomUser.all_objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_object(self):
        try:
            user = self.queryset.get(pk=self.kwargs["pk"])
            if user.is_deleted:
                raise NotFound(
                    detail="User not found."
                )  # Prevent accessing soft-deleted users
            return user
        except CustomUser.DoesNotExist:
            raise NotFound(detail="User not found.")

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()

    def get_serializer_context(self):
        return {"request": self.request}


class EmployeesListView(generics.ListCreateAPIView):
    serializer_class = EmployeesSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = CustomUser.objects.exclude(role="admin").filter(is_deleted=False)
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = [
        "username",
        "contact_number",
        "first_name",
        "last_name",
        "email",
        "address",
        "province",
        "city",
        "barangay",
    ]
    search_fields = [
        "username",
        "contact_number",
        "first_name",
        "last_name",
        "email",
        "address",
        "province",
        "city",
        "barangay",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        return filter_by_date_range(self.request, super().get_queryset())


class UseraDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EmployeesSerializer
    queryset = CustomUser.objects.filter(is_deleted=False)
    permission_classes = [permissions.IsAuthenticated]

    def filter_queryset(self, queryset):
        return queryset

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()

    def get_serializer_context(self):
        return {"request": self.request}


class MyProfileView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        if self.request.user.is_deleted:
            raise NotFound(detail="User not found.")
        return self.request.user

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()

    def get_serializer_context(self):
        return {"request": self.request}


class SystemSettingsView(generics.RetrieveUpdateAPIView):
    """
    GET: Retrieve system settings (any authenticated user can view)
    PUT/PATCH: Update system settings (admin only)
    """
    serializer_class = SystemSettingsSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        """Always return the singleton settings instance"""
        return SystemSettings.get_settings()
    
    def get_permissions(self):
        """Allow any authenticated user to view, but only admins to update"""
        if self.request.method in ['PUT', 'PATCH']:
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]


class CashAdvanceMovementViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing cash ban balance movements.
    - List: View all movements (admin/manager) or own movements (employee)
    - Create: Record a new movement — credit (+) or debit (-) (admin/manager only)
    - Retrieve/Delete: Manage specific movement (admin/manager only)
    """
    serializer_class = CashAdvanceMovementSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ['employee', 'date', 'movement_type']
    search_fields = ['employee__first_name', 'employee__last_name', 'description', 'reference']
    ordering_fields = ['date', 'amount', 'created_at']
    ordering = ['-date', '-created_at']

    def get_queryset(self):
        """
        Admin/Manager: See all movements
        Other users: See only their own movements
        """
        queryset = CashAdvanceMovement.objects.filter(is_deleted=False).select_related(
            'employee', 'created_by'
        )

        user = self.request.user
        if user.role in ['admin', 'manager']:
            return filter_by_date_range(self.request, queryset)
        else:
            return queryset.filter(employee=user)

    def get_permissions(self):
        """Only admin/manager can create, update, or delete"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdminOrManager()]
        return [permissions.IsAuthenticated()]

    def perform_destroy(self, instance):
        """Soft delete and reverse the balance change (only if movement was already applied)"""
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted'])
        # Only reverse the balance change if the movement was already applied (not pending)
        if not instance.is_pending:
            if instance.movement_type == CashAdvanceMovement.MovementType.CREDIT:
                instance.employee.cash_ban_balance -= instance.amount
            else:
                instance.employee.cash_ban_balance += instance.amount
            instance.employee.save(update_fields=['cash_ban_balance'])


class IsAdminOrManager(permissions.BasePermission):
    """Permission class to check if user is admin or manager"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['admin', 'manager']
