from rest_framework import serializers
from surveillance.models import CCTVCamera


class CCTVCameraSerializer(serializers.ModelSerializer):
    stream_name = serializers.ReadOnlyField()

    class Meta:
        model = CCTVCamera
        fields = [
            "id",
            "name",
            "stream_url",
            "location",
            "notes",
            "is_active",
            "order",
            "stream_name",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            # stream_url contains credentials — write-only, never exposed in list responses
            "stream_url": {"write_only": True},
        }


class CCTVCameraListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the camera grid (no credentials)."""

    stream_name = serializers.ReadOnlyField()

    class Meta:
        model = CCTVCamera
        fields = [
            "id",
            "name",
            "location",
            "is_active",
            "order",
            "stream_name",
        ]
