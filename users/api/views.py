from rest_framework import generics, permissions, filters
from rest_framework.exceptions import NotFound
from utils.query import filter_by_date_range
from users.models import CustomUser
from users.api.serializers import EmployeesSerializer, UserSerializer
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
