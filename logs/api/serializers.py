from rest_framework import serializers
from logs.models import ActivityLog


class ActivityLogSerializer(serializers.ModelSerializer):
    content_object = serializers.SerializerMethodField()
    content_type = serializers.StringRelatedField()
    performed_by = serializers.StringRelatedField()

    class Meta:
        model = ActivityLog
        fields = "__all__"

    def get_content_object(self, obj):
        return str(obj.content_object)
