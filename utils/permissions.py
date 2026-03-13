from rest_framework.permissions import IsAuthenticated


class IsAdminOrManager(IsAuthenticated):
    """Allow only admin and manager roles."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.role in ("admin", "manager")
