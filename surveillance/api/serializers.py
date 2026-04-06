from rest_framework import serializers
from surveillance.models import CCTVCamera


class CCTVCameraSerializer(serializers.ModelSerializer):
    stream_name = serializers.ReadOnlyField()

    class Meta:
        model = CCTVCamera
        fields = [
            "id",
            "name",
            "uid",
            "username",
            "password",
            "channel",
            "location",
            "notes",
            "is_active",
            "order",
            "stream_name",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            # Password is write-only on the API — never exposed in responses
            "password": {"write_only": True},
        }


class CCTVCameraListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the camera grid (no credentials)."""

    stream_name = serializers.ReadOnlyField()

    class Meta:
        model = CCTVCamera
        fields = [
            "id",
            "name",
            "channel",
            "location",
            "is_active",
            "order",
            "stream_name",
        ]
