"""
Analytics API Serializers

Serializers for calendar events.
"""
from rest_framework import serializers
from analytics.models import CalendarEvent
from users.models import CustomUser


class CalendarEventSerializer(serializers.ModelSerializer):
    """Serializer for CalendarEvent model."""
    
    created_by_name = serializers.SerializerMethodField()
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    
    class Meta:
        model = CalendarEvent
        fields = [
            'id',
            'title',
            'description',
            'event_date',
            'event_type',
            'event_type_display',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
            'is_deleted',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'created_by_name']
    
    def get_created_by_name(self, obj):
        """Get full name of the user who created the event."""
        if obj.created_by:
            return obj.created_by.get_full_name()
        return None
    
    def create(self, validated_data):
        """Set created_by to current user."""
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class CalendarEventListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for calendar event lists."""
    
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    
    class Meta:
        model = CalendarEvent
        fields = [
            'id',
            'title',
            'event_date',
            'event_type',
            'event_type_display',
        ]
