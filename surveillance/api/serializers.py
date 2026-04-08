from rest_framework import serializers
from surveillance.models import CCTVCamera


class CCTVCameraSerializer(serializers.ModelSerializer):
    class Meta:
        model = CCTVCamera
        fields = [
            "id",
            "name",
            "stream_name",
            "stream_url",
            "location",
            "notes",
            "is_active",
            "order",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "stream_url": {"write_only": True, "required": False},
        }


class CCTVCameraListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the camera grid (no credentials)."""

    class Meta:
        model = CCTVCamera
        fields = [
            "id",
            "name",
            "stream_name",
            "location",
            "is_active",
            "order",
        ]
