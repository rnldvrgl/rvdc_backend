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
    technicians = ScheduleTechnicianSerializer(many=True, read_only=True)
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)
    technician_count = serializers.SerializerMethodField()

    class Meta:
        model = Schedule
        fields = [
            'id',
            'client',
            'technicians',
            'technician_count',
            'scheduled_datetime',
            'service_type',
            'service_type_display',
            'notes',
            'created_at',
        ]

    def get_technician_count(self, obj):
        return obj.technicians.count()


class ScheduleDetailSerializer(serializers.ModelSerializer):
    """Serializer for schedule details with full nested data"""
    client = ScheduleClientSerializer(read_only=True)
    technicians = ScheduleTechnicianSerializer(many=True, read_only=True)
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)
    technician_count = serializers.SerializerMethodField()
    technician_names = serializers.CharField(source='get_technician_names', read_only=True)

    class Meta:
        model = Schedule
        fields = [
            'id',
            'client',
            'technicians',
            'technician_count',
            'technician_names',
            'scheduled_datetime',
            'service_type',
            'service_type_display',
            'notes',
            'created_at',
        ]

    def get_technician_count(self, obj):
        return obj.technicians.count()


class ScheduleCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating schedules with multiple technicians"""
    technicians = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CustomUser.objects.filter(role='technician', is_deleted=False),
        required=False,
        allow_empty=True
    )

    class Meta:
        model = Schedule
        fields = [
            'id',
            'client',
            'technicians',
            'scheduled_datetime',
            'service_type',
            'notes',
        ]

    def validate_client(self, value):
        """Validate that client exists and is not deleted"""
        if not Client.objects.filter(id=value.id, is_deleted=False).exists():
            raise serializers.ValidationError("Client not found or has been deleted.")
        return value

    def validate_technicians(self, value):
        """Validate that all technicians exist and are valid"""
        if value:
            for technician in value:
                if not CustomUser.objects.filter(
                    id=technician.id,
                    is_deleted=False,
                    role='technician'
                ).exists():
                    raise serializers.ValidationError(
                        f"Technician {technician.id} not found, has been deleted, or is not a technician."
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

        technicians = data.get('technicians', [])
        scheduled_datetime = data.get('scheduled_datetime')

        if technicians and scheduled_datetime:
            # Check for overlapping schedules (within 2 hours) for each technician
            time_buffer = timedelta(hours=2)
            start_time = scheduled_datetime - time_buffer
            end_time = scheduled_datetime + time_buffer

            conflicts = []
            for technician in technicians:
                conflicting_schedules = Schedule.objects.filter(
                    technicians=technician,
                    scheduled_datetime__range=(start_time, end_time)
                )

                # Exclude current instance when updating
                if self.instance:
                    conflicting_schedules = conflicting_schedules.exclude(id=self.instance.id)

                if conflicting_schedules.exists():
                    conflicts.append({
                        'technician': technician.get_full_name(),
                        'schedules': conflicting_schedules.count()
                    })

            if conflicts:
                conflict_messages = [
                    f"{conflict['technician']} has {conflict['schedules']} conflicting schedule(s)"
                    for conflict in conflicts
                ]
                raise serializers.ValidationError({
                    'technicians': conflict_messages
                })

        return data

    def create(self, validated_data):
        """Create schedule with multiple technicians"""
        technicians = validated_data.pop('technicians', [])
        schedule = Schedule.objects.create(**validated_data)
        if technicians:
            schedule.technicians.set(technicians)
        return schedule

    def update(self, instance, validated_data):
        """Update schedule with multiple technicians"""
        technicians = validated_data.pop('technicians', None)

        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update technicians if provided
        if technicians is not None:
            instance.technicians.set(technicians)

        return instance

