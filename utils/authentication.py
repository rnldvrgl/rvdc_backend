from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ActiveUserJWTAuthentication(JWTAuthentication):
    """
    Extends SimpleJWT authentication to reject tokens belonging to
    deleted or inactive users.

    When an employee (clerk, manager, technician) is archived/deactivated,
    any existing JWT tokens they hold will be rejected immediately.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if getattr(user, "is_deleted", False):
            raise AuthenticationFailed("Account is no longer active.")

        if not getattr(user, "is_active", True):
            raise AuthenticationFailed("Account is no longer active.")

        return user
