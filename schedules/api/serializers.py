from clients.models import Client
from rest_framework import serializers
from schedules.models import Schedule
from users.models import CustomUser


class ScheduleClientSerializer(serializers.ModelSerializer):
    """Nested serializer for client data in schedules"""
    class Meta:
        model = Client
        fields = ['id', 'full_name', 'contact_number', 'address', 'city', 'province']


class ScheduleTechnicianSerializer(serializers.ModelSerializer):
    """Nested serializer for technician data in schedules"""
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'first_name', 'last_name', 'full_name', 'contact_number']

    def get_full_name(self, obj):
        return obj.get_full_name()


class ScheduleListSerializer(serializers.ModelSerializer):
    """Serializer for listing schedules with nested data"""
    client = ScheduleClientSerializer(read_only=True)
    technician = ScheduleTechnicianSerializer(read_only=True)
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)

    class Meta:
        model = Schedule
        fields = [
            'id',
            'client',
            'technician',
            'scheduled_datetime',
            'service_type',
            'service_type_display',
            'notes',
            'created_at',
        ]


class ScheduleDetailSerializer(serializers.ModelSerializer):
    """Serializer for schedule details with full nested data"""
    client = ScheduleClientSerializer(read_only=True)
    technician = ScheduleTechnicianSerializer(read_only=True)
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)

    class Meta:
        model = Schedule
        fields = [
            'id',
            'client',
            'technician',
            'scheduled_datetime',
            'service_type',
            'service_type_display',
            'notes',
            'created_at',
        ]


class ScheduleCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating schedules"""

    class Meta:
        model = Schedule
        fields = [
            'id',
            'client',
            'technician',
            'scheduled_datetime',
            'service_type',
            'notes',
        ]

    def validate_client(self, value):
        """Validate that client exists and is not deleted"""
        if not Client.objects.filter(id=value.id, is_deleted=False).exists():
            raise serializers.ValidationError("Client not found or has been deleted.")
        return value

    def validate_technician(self, value):
        """Validate that technician exists and is not deleted"""
        if value and not CustomUser.objects.filter(
            id=value.id,
            is_deleted=False,
            role='technician'
        ).exists():
            raise serializers.ValidationError(
                "Technician not found, has been deleted, or is not a technician."
            )
        return value

    def validate_scheduled_datetime(self, value):
        """Validate that scheduled datetime is in the future"""
        from django.utils import timezone
        if value < timezone.now():
            raise serializers.ValidationError(
                "Scheduled datetime must be in the future."
            )
        return value

    def validate(self, data):
        """Additional validation for schedule conflicts"""
        from datetime import timedelta


        technician = data.get('technician')
        scheduled_datetime = data.get('scheduled_datetime')

        if technician and scheduled_datetime:
            # Check for overlapping schedules (within 2 hours)
            time_buffer = timedelta(hours=2)
            start_time = scheduled_datetime - time_buffer
            end_time = scheduled_datetime + time_buffer

            conflicting_schedules = Schedule.objects.filter(
                technician=technician,
                scheduled_datetime__range=(start_time, end_time)
            )

            # Exclude current instance when updating
            if self.instance:
                conflicting_schedules = conflicting_schedules.exclude(id=self.instance.id)

            if conflicting_schedules.exists():
                raise serializers.ValidationError({
                    'scheduled_datetime':
                        f"Technician {technician.get_full_name()} has another schedule "
                        f"within 2 hours of this time."
                })

        return data
