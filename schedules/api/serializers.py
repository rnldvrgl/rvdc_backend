"""
API serializers for scheduling system.

Handles:
- Schedule creation from services (home_service, pull_out_return)
- Technician daily schedules
- Schedule status updates
- Conflict checking
"""

from clients.models import Client
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from schedules.models import (
    Schedule,
    ScheduleStatus,
    ScheduleStatusHistory,
    ScheduleType,
)
from services.models import Service
from users.models import CustomUser
from utils.enums import ServiceMode


class ScheduleSerializer(serializers.ModelSerializer):
    """Main serializer for Schedule model."""

    client_name = serializers.CharField(source="client.name", read_only=True)
    technician_name = serializers.CharField(
        source="technician.get_full_name", read_only=True
    )
    service_id = serializers.PrimaryKeyRelatedField(
        source="service", queryset=Service.objects.all(), write_only=True, required=False
    )
    client_id = serializers.PrimaryKeyRelatedField(
        source="client", queryset=Client.objects.all(), write_only=True
    )
    technician_id = serializers.PrimaryKeyRelatedField(
        source="technician",
        queryset=CustomUser.objects.filter(role="technician", is_active=True),
        write_only=True,
        required=False,
        allow_null=True,
    )

    # Read-only computed fields
    is_completed = serializers.BooleanField(read_only=True)
    is_cancelled = serializers.BooleanField(read_only=True)
    actual_duration_minutes = serializers.IntegerField(read_only=True)
    location_address = serializers.CharField(read_only=True)
    location_contact_person = serializers.CharField(read_only=True)
    location_contact_number = serializers.CharField(read_only=True)

    class Meta:
        model = Schedule
        fields = [
            "id",
            "service",
            "service_id",
            "client",
            "client_id",
            "client_name",
            "technician",
            "technician_id",
            "technician_name",
            "schedule_type",
            "scheduled_date",
            "scheduled_time",
            "estimated_duration",
            "status",
            "address",
            "contact_person",
            "contact_number",
            "notes",
            "internal_notes",
            "actual_start_time",
            "actual_end_time",
            "completed_by",
            "created_at",
            "updated_at",
            "created_by",
            "is_completed",
            "is_cancelled",
            "actual_duration_minutes",
            "location_address",
            "location_contact_person",
            "location_contact_number",
        ]
        read_only_fields = [
            "actual_start_time",
            "actual_end_time",
            "completed_by",
            "created_at",
            "updated_at",
            "created_by",
        ]

    def validate(self, data):
        """Validate schedule data."""
        # Validate technician role
        technician = data.get("technician")
        if technician and technician.role != "technician":
            raise serializers.ValidationError(
                {"technician": "Assigned user must have technician role."}
            )

        # Validate service mode matches schedule type
        service = data.get("service")
        schedule_type = data.get("schedule_type")

        if service and schedule_type:
            if service.service_mode == ServiceMode.HOME_SERVICE:
                if schedule_type not in [ScheduleType.HOME_SERVICE, ScheduleType.ON_SITE]:
                    raise serializers.ValidationError(
                        {
                            "schedule_type": "Schedule type must be home_service or on_site for home_service mode."
                        }
                    )
            elif service.service_mode == ServiceMode.PULL_OUT_RETURN:
                if schedule_type not in [ScheduleType.PULL_OUT, ScheduleType.RETURN]:
                    raise serializers.ValidationError(
                        {
                            "schedule_type": "Schedule type must be pull_out or return for pull_out_return service mode."
                        }
                    )
            elif service.service_mode == ServiceMode.IN_SHOP:
                raise serializers.ValidationError(
                    {"service": "Cannot create schedule for in-shop services."}
                )

        return data

    def create(self, validated_data):
        """Create schedule with user tracking."""
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            validated_data["created_by"] = request.user

        return super().create(validated_data)


class ScheduleCreateFromServiceSerializer(serializers.Serializer):
    """Serializer for creating schedules from a service."""

    service_id = serializers.IntegerField(help_text="Service ID to create schedule for")
    schedule_type = serializers.ChoiceField(
        choices=ScheduleType.choices, help_text="Type of schedule"
    )
    scheduled_date = serializers.DateField(
        required=False, allow_null=True, help_text="Date (uses service date if not provided)"
    )
    scheduled_time = serializers.TimeField(
        required=False, allow_null=True, help_text="Time (uses service time if not provided)"
    )
    technician_id = serializers.IntegerField(
        required=False, allow_null=True, help_text="Technician ID (optional)"
    )
    estimated_duration = serializers.IntegerField(
        required=False, allow_null=True, help_text="Duration in minutes"
    )
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_service_id(self, value):
        """Validate service exists."""
        if not Service.objects.filter(id=value).exists():
            raise serializers.ValidationError("Service not found.")
        return value

    def validate_technician_id(self, value):
        """Validate technician exists."""
        if value and not CustomUser.objects.filter(
            id=value, role="technician", is_active=True
        ).exists():
            raise serializers.ValidationError("Technician not found or inactive.")
        return value

    def save(self):
        """Create schedule from service."""
        from schedules.business_logic import ScheduleManager

        service = Service.objects.get(id=self.validated_data["service_id"])
        technician = None
        if self.validated_data.get("technician_id"):
            technician = CustomUser.objects.get(id=self.validated_data["technician_id"])

        user = self.context.get("request").user if self.context.get("request") else None

        schedule = ScheduleManager.create_schedule_from_service(
            service=service,
            schedule_type=self.validated_data["schedule_type"],
            scheduled_date=self.validated_data.get("scheduled_date"),
            scheduled_time=self.validated_data.get("scheduled_time"),
            technician=technician,
            estimated_duration=self.validated_data.get("estimated_duration"),
            notes=self.validated_data.get("notes", ""),
            user=user,
        )

        return schedule


class PullOutReturnScheduleSerializer(serializers.Serializer):
    """Serializer for creating pull-out and return schedules."""

    service_id = serializers.IntegerField(help_text="Service ID (must be pull_out_return mode)")
    pull_out_date = serializers.DateField(help_text="Date for pull-out")
    pull_out_time = serializers.TimeField(help_text="Time for pull-out")
    return_date = serializers.DateField(help_text="Date for return")
    return_time = serializers.TimeField(help_text="Time for return")
    technician_id = serializers.IntegerField(
        required=False, allow_null=True, help_text="Technician ID (optional)"
    )

    def validate_service_id(self, value):
        """Validate service exists and is pull_out_return mode."""
        try:
            service = Service.objects.get(id=value)
        except Service.DoesNotExist:
            raise serializers.ValidationError("Service not found.")

        if service.service_mode != ServiceMode.PULL_OUT_RETURN:
            raise serializers.ValidationError(
                "Service must have pull_out_return mode for this operation."
            )

        return value

    def validate_technician_id(self, value):
        """Validate technician exists."""
        if value and not CustomUser.objects.filter(
            id=value, role="technician", is_active=True
        ).exists():
            raise serializers.ValidationError("Technician not found or inactive.")
        return value

    def validate(self, data):
        """Validate return is after pull-out."""
        from datetime import datetime

        pull_out_dt = datetime.combine(data["pull_out_date"], data["pull_out_time"])
        return_dt = datetime.combine(data["return_date"], data["return_time"])

        if return_dt <= pull_out_dt:
            raise serializers.ValidationError("Return must be scheduled after pull-out.")

        return data

    def save(self):
        """Create both pull-out and return schedules."""
        from schedules.business_logic import create_pull_out_return_schedules

        service = Service.objects.get(id=self.validated_data["service_id"])
        technician = None
        if self.validated_data.get("technician_id"):
            technician = CustomUser.objects.get(id=self.validated_data["technician_id"])

        user = self.context.get("request").user if self.context.get("request") else None

        result = create_pull_out_return_schedules(
            service=service,
            pull_out_date=self.validated_data["pull_out_date"],
            pull_out_time=self.validated_data["pull_out_time"],
            return_date=self.validated_data["return_date"],
            return_time=self.validated_data["return_time"],
            technician=technician,
            user=user,
        )

        return result


class ScheduleStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating schedule status."""

    status = serializers.ChoiceField(choices=ScheduleStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def save(self):
        """Update schedule status."""
        from schedules.business_logic import ScheduleManager

        schedule = self.context.get("schedule")
        if not schedule:
            raise ValidationError("Schedule instance required in context.")

        user = self.context.get("request").user if self.context.get("request") else None

        return ScheduleManager.update_schedule_status(
            schedule=schedule,
            new_status=self.validated_data["status"],
            notes=self.validated_data.get("notes"),
            user=user,
        )


class ScheduleRescheduleSerializer(serializers.Serializer):
    """Serializer for rescheduling an appointment."""

    new_date = serializers.DateField(help_text="New scheduled date")
    new_time = serializers.TimeField(help_text="New scheduled time")
    technician_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="New technician (optional, keeps existing if not provided)",
    )
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate_technician_id(self, value):
        """Validate technician exists."""
        if value and not CustomUser.objects.filter(
            id=value, role="technician", is_active=True
        ).exists():
            raise serializers.ValidationError("Technician not found or inactive.")
        return value

    def save(self):
        """Reschedule the appointment."""
        from schedules.business_logic import ScheduleManager

        schedule = self.context.get("schedule")
        if not schedule:
            raise ValidationError("Schedule instance required in context.")

        technician = None
        if self.validated_data.get("technician_id"):
            technician = CustomUser.objects.get(id=self.validated_data["technician_id"])

        user = self.context.get("request").user if self.context.get("request") else None

        return ScheduleManager.reschedule(
            schedule=schedule,
            new_date=self.validated_data["new_date"],
            new_time=self.validated_data["new_time"],
            technician=technician,
            reason=self.validated_data.get("reason"),
            user=user,
        )


class ScheduleStatusHistorySerializer(serializers.ModelSerializer):
    """Serializer for schedule status history."""

    changed_by_name = serializers.CharField(source="changed_by.get_full_name", read_only=True)

    class Meta:
        model = ScheduleStatusHistory
        fields = ["id", "status", "notes", "changed_by", "changed_by_name", "changed_at"]


class TechnicianAvailabilitySerializer(serializers.Serializer):
    """Serializer for checking technician availability."""

    technician_id = serializers.IntegerField()
    schedule_date = serializers.DateField()
    start_time = serializers.TimeField()
    duration_minutes = serializers.IntegerField(default=60)

    def validate_technician_id(self, value):
        """Validate technician exists."""
        if not CustomUser.objects.filter(
            id=value, role="technician", is_active=True
        ).exists():
            raise serializers.ValidationError("Technician not found or inactive.")
        return value
