from rest_framework.permissions import IsAuthenticated


class IsActiveUser(IsAuthenticated):
    """
    Reject requests from deleted or inactive users.

    This ensures that even if a user has a valid JWT token, they cannot
    perform any actions if their account has been deactivated or deleted.
    """
    message = "Your account has been deactivated. Please contact an administrator."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        if getattr(user, "is_deleted", False) or not getattr(user, "is_active", True):
            return False
        return True


class IsAdminOrManager(IsActiveUser):
    """Allow only active admin and manager roles."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.role in ("admin", "manager")
