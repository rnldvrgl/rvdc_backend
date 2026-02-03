from clients.models import Client
from rest_framework import serializers
from services.models import Service
from users.models import CustomUser

from schedules.models import Schedule, ScheduleStatusHistory


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


class ScheduleServiceSerializer(serializers.ModelSerializer):
    """Nested serializer for service data in schedules"""
    from services.api.serializers import ServiceSerializer

    class Meta:
        model = Service
        fields = ['id', 'service_type', 'status', 'total_amount']


class ScheduleStatusHistorySerializer(serializers.ModelSerializer):
    """Serializer for schedule status history"""
    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ScheduleStatusHistory
        fields = ['id', 'status', 'status_display', 'notes', 'changed_at', 'changed_by', 'changed_by_name']


class ScheduleListSerializer(serializers.ModelSerializer):
    """Serializer for listing schedules with nested data"""
    client = ScheduleClientSerializer(read_only=True)
    technicians = ScheduleTechnicianSerializer(many=True, read_only=True)
    schedule_type_display = serializers.CharField(source='get_schedule_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    technician_count = serializers.SerializerMethodField()
    is_overdue = serializers.ReadOnlyField()

    class Meta:
        model = Schedule
        fields = [
            'id',
            'client',
            'service',
            'technicians',
            'technician_count',
            'schedule_type',
            'schedule_type_display',
            'scheduled_date',
            'scheduled_time',
            'status',
            'status_display',
            'estimated_duration',
            'is_overdue',
            'notes',
            'created_at',
        ]

    def get_technician_count(self, obj):
        return obj.technicians.count()


class ScheduleDetailSerializer(serializers.ModelSerializer):
    """Serializer for schedule details with full nested data"""
    client = ScheduleClientSerializer(read_only=True)
    technicians = ScheduleTechnicianSerializer(many=True, read_only=True)
    schedule_type_display = serializers.CharField(source='get_schedule_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    technician_count = serializers.SerializerMethodField()
    technician_names = serializers.CharField(source='get_technician_names', read_only=True)
    status_history = ScheduleStatusHistorySerializer(many=True, read_only=True)
    is_overdue = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    completed_by_name = serializers.CharField(source='completed_by.get_full_name', read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, allow_null=True)

    class Meta:
        model = Schedule
        fields = [
            'id',
            'client',
            'service',
            'technicians',
            'technician_count',
            'technician_names',
            'schedule_type',
            'schedule_type_display',
            'scheduled_date',
            'scheduled_time',
            'estimated_duration',
            'status',
            'status_display',
            'address',
            'contact_person',
            'contact_number',
            'notes',
            'internal_notes',
            'actual_start_time',
            'actual_end_time',
            'completed_by',
            'completed_by_name',
            'is_overdue',
            'is_completed',
            'status_history',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name',
        ]

    def get_technician_count(self, obj):
        return obj.technicians.count()


class ScheduleCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating schedules"""
    technicians = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CustomUser.objects.filter(role='technician', is_deleted=False),
        required=False,
        allow_empty=True
    )
    service = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Schedule
        fields = [
            'id',
            'client',
            'service',
            'technicians',
            'schedule_type',
            'scheduled_date',
            'scheduled_time',
            'estimated_duration',
            'status',
            'address',
            'contact_person',
            'contact_number',
            'notes',
            'internal_notes',
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

    def validate_scheduled_date(self, value):
        """Validate that scheduled date is not in the past"""

        from django.utils import timezone

        if value < timezone.now().date():
            raise serializers.ValidationError(
                "Scheduled date cannot be in the past."
            )
        return value

    def validate(self, data):
        """Additional validation for schedule conflicts"""
        from datetime import datetime, timedelta

        from django.utils import timezone

        technicians = data.get('technicians', [])
        scheduled_date = data.get('scheduled_date')
        scheduled_time = data.get('scheduled_time')
        estimated_duration = data.get('estimated_duration', 60)

        if technicians and scheduled_date and scheduled_time:
            # Combine date and time for conflict checking
            scheduled_datetime = timezone.make_aware(
                datetime.combine(scheduled_date, scheduled_time)
            )

            # Check for overlapping schedules
            duration_buffer = timedelta(minutes=estimated_duration)
            start_time = scheduled_datetime - duration_buffer
            end_time = scheduled_datetime + duration_buffer

            conflicts = []
            for technician in technicians:
                # Find schedules for this technician on the same date
                conflicting_schedules = Schedule.objects.filter(
                    technicians=technician,
                    scheduled_date=scheduled_date,
                    status__in=['pending', 'confirmed', 'in_progress']
                )

                # Exclude current instance when updating
                if self.instance:
                    conflicting_schedules = conflicting_schedules.exclude(id=self.instance.id)

                # Check time overlaps
                for schedule in conflicting_schedules:
                    other_datetime = timezone.make_aware(
                        datetime.combine(schedule.scheduled_date, schedule.scheduled_time)
                    )
                    other_duration = timedelta(minutes=schedule.estimated_duration)

                    # Check if time ranges overlap
                    if not (scheduled_datetime + duration_buffer <= other_datetime or
                            scheduled_datetime >= other_datetime + other_duration):
                        conflicts.append({
                            'technician': technician.get_full_name(),
                            'time': schedule.scheduled_time.strftime('%H:%M')
                        })
                        break

            if conflicts:
                conflict_messages = [
                    f"{conflict['technician']} has a conflicting schedule at {conflict['time']}"
                    for conflict in conflicts
                ]
                raise serializers.ValidationError({
                    'technicians': conflict_messages
                })

        return data

    def create(self, validated_data):
        """Create schedule with multiple technicians"""
        technicians = validated_data.pop('technicians', [])

        # Set created_by from request user
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user

        schedule = Schedule.objects.create(**validated_data)

        if technicians:
            schedule.technicians.set(technicians)

        # Create initial status history
        ScheduleStatusHistory.objects.create(
            schedule=schedule,
            status=schedule.status,
            notes='Schedule created',
            changed_by=validated_data.get('created_by')
        )

        return schedule

    def update(self, instance, validated_data):
        """Update schedule with multiple technicians"""
        technicians = validated_data.pop('technicians', None)
        old_status = instance.status

        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update technicians if provided
        if technicians is not None:
            instance.technicians.set(technicians)

        # Create status history if status changed
        new_status = instance.status
        if old_status != new_status:
            request = self.context.get('request')
            changed_by = request.user if request and hasattr(request, 'user') else None

            ScheduleStatusHistory.objects.create(
                schedule=instance,
                status=new_status,
                notes=f'Status changed from {old_status} to {new_status}',
                changed_by=changed_by
            )

        return instance
