from rest_framework import serializers
from django.contrib.auth import authenticate
from utils.tokens import get_tokens_for_user
from users.models import CustomUser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from users.api.serializers import UserSerializer


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

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
        except TokenError as e:
            raise serializers.ValidationError({"refresh": "Invalid or expired token."})
