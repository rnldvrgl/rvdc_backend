from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from authentication.models import AuthSession


class ActiveUserJWTAuthentication(JWTAuthentication):
    """
    Extends SimpleJWT authentication to:
    1. Reject tokens belonging to deleted or inactive users.
    2. Reject access tokens whose corresponding AuthSession has been revoked.
       This allows instant forced-logout when an admin revokes a session.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if getattr(user, "is_deleted", False):
            raise AuthenticationFailed("Account is no longer active.")

        if not getattr(user, "is_active", True):
            raise AuthenticationFailed("Account is no longer active.")

        # Check if the session tied to this access token has been revoked.
        access_jti = str(validated_token.get("jti", ""))
        if access_jti:
            session = AuthSession.objects.filter(
                access_jti=access_jti, user=user
            ).first()
            if session is not None and not session.is_active:
                raise AuthenticationFailed("Session has been revoked.")

        return user
