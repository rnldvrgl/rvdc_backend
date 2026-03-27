from rest_framework import serializers
from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone
from utils.tokens import get_tokens_for_user
from users.models import CustomUser
from authentication.models import AuthSession
from authentication.session_tracking import (
    revoke_session_by_refresh,
    rotate_session_refresh,
    upsert_login_session,
)
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from users.api.serializers import UserSerializer


def enforce_active_session_limit(user, current_refresh_token: str) -> None:
    """Blacklist oldest active refresh tokens above configured per-user limit."""
    max_sessions = getattr(settings, "AUTH_MAX_ACTIVE_SESSIONS", 0)
    if max_sessions <= 0:
        return

    try:
        current_jti = RefreshToken(current_refresh_token)["jti"]
    except Exception:
        current_jti = None

    active_tokens = OutstandingToken.objects.filter(
        user=user,
        blacklistedtoken__isnull=True,
    )

    if current_jti:
        active_tokens = active_tokens.exclude(jti=current_jti)

    # Keep one slot for the token issued in this login event.
    keep_other_tokens = max(max_sessions - 1, 0)
    tokens_to_blacklist = active_tokens.order_by("-created_at")[keep_other_tokens:]

    for outstanding in tokens_to_blacklist:
        try:
            BlacklistedToken.objects.get_or_create(token=outstanding)
            AuthSession.objects.filter(refresh_jti=outstanding.jti).update(
                is_active=False,
                revoked_at=timezone.now(),
                last_seen_at=timezone.now(),
            )
        except Exception:
            # Best-effort to avoid blocking login on cleanup issues.
            continue


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    device_id = serializers.CharField(required=False, allow_blank=True, max_length=128)

    def validate(self, data):
        user = authenticate(
            username=data.get("username"), password=data.get("password")
        )

        if not user:
            # Also check if the user exists but is inactive (Django's authenticate
            # returns None for inactive users by default)
            from users.models import CustomUser
            try:
                existing = CustomUser.all_objects.get(username=data.get("username"))
                if existing.is_deleted or not existing.is_active:
                    raise serializers.ValidationError("Account is no longer active.")
            except CustomUser.DoesNotExist:
                pass
            raise serializers.ValidationError("Invalid credentials.")

        if user.is_deleted:
            raise serializers.ValidationError("Account is no longer active.")

        if not user.is_active:
            raise serializers.ValidationError("Account is no longer active.")

        tokens = get_tokens_for_user(user)
        enforce_active_session_limit(user, tokens["refresh"])

        request = self.context.get("request")
        upsert_login_session(
            user,
            tokens["refresh"],
            request=request,
            device_id=data.get("device_id", ""),
        )

        user_data = UserSerializer(user, context=self.context).data

        return {
            **user_data,
            "access": tokens["access"],
            "refresh": tokens["refresh"],
        }


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = (
            "username",
            "password",
            "email",
            "first_name",
            "last_name",
            "role",
            "birthday",
            "address",
            "contact_number",
            "profile_image",
        )
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def create(self, validated_data):
        user = CustomUser.objects.create_user(**validated_data)

        tokens = get_tokens_for_user(user)
        user_data = {
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": f"{user.first_name} {user.last_name}",
            "profile_image": user.profile_image.url if user.profile_image else None,
            "role": user.role,
            "birthday": user.birthday,
            "address": user.address,
            "contact_number": user.contact_number,
            "access": tokens["access"],
            "refresh": tokens["refresh"],
        }

        return user_data

    def update(self, instance, validated_data):
        instance.username = validated_data.get("username", instance.username)
        instance.email = validated_data.get("email", instance.email)
        instance.first_name = validated_data.get("first_name", instance.first_name)
        instance.last_name = validated_data.get("last_name", instance.last_name)
        instance.role = validated_data.get("role", instance.role)
        instance.birthday = validated_data.get("birthday", instance.birthday)
        instance.address = validated_data.get("address", instance.address)
        instance.contact_number = validated_data.get(
            "contact_number", instance.contact_number
        )
        instance.profile_image = validated_data.get(
            "profile_image", instance.profile_image
        )
        instance.save()
        return instance


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate(self, attrs):
        self.token = attrs["refresh"]
        return attrs

    def save(self, **kwargs):
        try:
            token = RefreshToken(self.token)
            token.blacklist()
            revoke_session_by_refresh(self.token)
        except TokenError as e:
            raise serializers.ValidationError({"refresh": "Invalid or expired token."})


class DeviceAwareTokenRefreshSerializer(TokenRefreshSerializer):
    device_id = serializers.CharField(required=False, allow_blank=True, max_length=128)

    def validate(self, attrs):
        device_id = attrs.get("device_id", "")
        old_refresh = attrs.get("refresh", "")
        data = super().validate(attrs)

        request = self.context.get("request")
        new_refresh = data.get("refresh") or old_refresh

        try:
            rotate_session_refresh(
                old_refresh_token=old_refresh,
                new_refresh_token=new_refresh,
                request=request,
                device_id=device_id,
            )
        except Exception:
            # Session tracking should not block token refresh.
            pass

        return data


class AuthSessionSerializer(serializers.ModelSerializer):
    is_current_device = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()

    class Meta:
        model = AuthSession
        fields = [
            "id",
            "user",
            "device_id",
            "device_label",
            "ip_address",
            "user_agent",
            "is_active",
            "is_current_device",
            "created_at",
            "last_seen_at",
            "expires_at",
            "revoked_at",
        ]

    def get_is_current_device(self, obj):
        current_device_id = self.context.get("device_id", "")
        return bool(current_device_id and obj.device_id == current_device_id)

    def get_user(self, obj):
        user = obj.user
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }
