from rest_framework import serializers
from django.contrib.auth import authenticate
from utils.tokens import get_tokens_for_user
from django.contrib.auth.models import User


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(
            username=data.get("username"), password=data.get("password")
        )

        if not user:
            raise serializers.ValidationError("Invalid credentials.")

        # Generate tokens
        tokens = get_tokens_for_user(user)

        return {
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": f"{user.first_name} {user.last_name}",
            "profile_image": user.profile_image.url if user.profile_image else None,
            "access": tokens["access"],
            "refresh": tokens["refresh"],
        }
