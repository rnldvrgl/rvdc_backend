"""
Business logic for scheduling workflows.

This module handles:
- Schedule creation from services (home_service, pull_out_return)
- Technician assignment
- Schedule status management
- Conflict detection and availability checking
"""

from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError


def get_available_technicians(schedule_date, start_time, duration_minutes=60):
    """
    Get technicians available for a given date and time slot.

    Args:
        schedule_date: Date of the schedule
        start_time: Start time of the schedule
        duration_minutes: Duration in minutes

    Returns:
        QuerySet of available technicians
    """
    from users.models import CustomUser

    from schedules.models import Schedule, ScheduleStatus

    # Get all technicians
    all_technicians = CustomUser.objects.filter(role='technician', is_active=True)

    # Calculate time window
    end_time = (
        datetime.combine(date.today(), start_time) +
        timedelta(minutes=duration_minutes)
    ).time()

    # Find technicians with conflicting schedules
    conflicting_schedules = Schedule.objects.filter(
        scheduled_date=schedule_date,
        status__in=[
            ScheduleStatus.PENDING,
            ScheduleStatus.CONFIRMED,
            ScheduleStatus.IN_PROGRESS
        ]
    ).exclude(
        Q(scheduled_time__gte=end_time) |  # Starts after this ends
        Q(scheduled_time__lt=start_time)    # Ends before this starts
    )

    busy_technician_ids = conflicting_schedules.values_list('technician_id', flat=True)

    # Return available technicians
    return all_technicians.exclude(id__in=busy_technician_ids)


class ScheduleManager:
    """Manages schedule creation and updates."""

    @staticmethod
    def create_schedule_from_service(service, schedule_type, scheduled_date=None,
                                     scheduled_time=None, technician=None,
                                     estimated_duration=None, user=None, **kwargs):
        """
        Create a schedule entry from a service.

        Args:
            service: Service instance
            schedule_type: Type of schedule (home_service, pull_out, return)
            scheduled_date: Date of schedule (uses service.scheduled_date if not provided)
            scheduled_time: Time of schedule (uses service.scheduled_time if not provided)
            technician: Assigned technician (optional)
            estimated_duration: Duration in minutes (uses service.estimated_duration if not provided)
            user: User creating the schedule
            **kwargs: Additional fields for Schedule model

        Returns:
            Schedule instance

        Raises:
            ValidationError: If validation fails
        """
        from utils.enums import ServiceMode

        from schedules.models import Schedule, ScheduleType

        # Validate service mode
        if service.service_mode == ServiceMode.IN_SHOP:
            raise ValidationError(
                "Cannot create schedule for in-shop services. "
                "Schedules are only for home_service and pull_out_return modes."
            )

        # Use service fields as defaults
        scheduled_date = scheduled_date or service.scheduled_date
        scheduled_time = scheduled_time or service.scheduled_time
        estimated_duration = estimated_duration or service.estimated_duration or 60

        if not scheduled_date:
            raise ValidationError("scheduled_date is required.")
        if not scheduled_time:
            raise ValidationError("scheduled_time is required.")

        # Validate schedule type matches service mode
        if service.service_mode == ServiceMode.HOME_SERVICE:
            if schedule_type not in [ScheduleType.HOME_SERVICE, ScheduleType.ON_SITE]:
                raise ValidationError(
                    "schedule_type must be home_service or on_site for home_service mode."
                )
        elif service.service_mode == ServiceMode.PULL_OUT_RETURN:
            if schedule_type not in [ScheduleType.PULL_OUT, ScheduleType.RETURN]:
                raise ValidationError(
                    "schedule_type must be pull_out or return for pull_out_return mode."
                )

        # Check technician availability if assigned
        if technician:
            available = get_available_technicians(
                scheduled_date,
                scheduled_time,
                estimated_duration
            )
            if technician not in available:
                raise ValidationError(
                    f"Technician {technician.get_full_name()} is not available at the requested time."
                )

        with transaction.atomic():
            # Create schedule
            schedule = Schedule.objects.create(
                service=service,
                client=service.client,
                technician=technician,
                schedule_type=schedule_type,
                scheduled_date=scheduled_date,
                scheduled_time=scheduled_time,
                estimated_duration=estimated_duration,
                address=kwargs.get('address') or service.override_address,
                contact_person=kwargs.get('contact_person') or service.override_contact_person,
                contact_number=kwargs.get('contact_number') or service.override_contact_number,
                notes=kwargs.get('notes') or service.description,
                internal_notes=kwargs.get('internal_notes'),
                created_by=user,
            )

            return schedule

    @staticmethod
    def create_pull_out_return_schedules(service, pull_out_date, pull_out_time,
                                         return_date, return_time,
                                         technician=None, user=None):
        """
        Create both pull-out and return schedules for a pull_out_return service.

        Args:
            service: Service instance (must be pull_out_return mode)
            pull_out_date: Date of pull-out
            pull_out_time: Time of pull-out
            return_date: Date of return
            return_time: Time of return
            technician: Assigned technician (optional)
            user: User creating the schedules

        Returns:
            dict with pull_out and return schedule instances
        """
        from utils.enums import ServiceMode

        from schedules.models import ScheduleType

        if service.service_mode != ServiceMode.PULL_OUT_RETURN:
            raise ValidationError(
                "Service must have pull_out_return mode to create pull-out and return schedules."
            )

        with transaction.atomic():
            # Create pull-out schedule
            pull_out_schedule = ScheduleManager.create_schedule_from_service(
                service=service,
                schedule_type=ScheduleType.PULL_OUT,
                scheduled_date=pull_out_date,
                scheduled_time=pull_out_time,
                technician=technician,
                user=user,
                notes="Pick-up appliance from client"
            )

            # Create return schedule
            return_schedule = ScheduleManager.create_schedule_from_service(
                service=service,
                schedule_type=ScheduleType.RETURN,
                scheduled_date=return_date,
                scheduled_time=return_time,
                technician=technician,
                user=user,
                notes="Return repaired appliance to client"
            )

            # Update service dates
            service.pickup_date = pull_out_date
            service.delivery_date = return_date
            service.save(update_fields=['pickup_date', 'delivery_date', 'updated_at'])

            return {
                'pull_out': pull_out_schedule,
                'return': return_schedule
            }

    @staticmethod
    def update_schedule_status(schedule, new_status, notes=None, user=None):
        """
        Update schedule status with history tracking.

        Args:
            schedule: Schedule instance
            new_status: New status value
            notes: Optional notes for status change
            user: User making the change

        Returns:
            Updated Schedule instance
        """
        from schedules.models import ScheduleStatusHistory

        if schedule.status == new_status:
            return schedule

        with transaction.atomic():
            old_status = schedule.status

            # Update schedule status
            schedule.status = new_status
            schedule.save(update_fields=['status', 'updated_at'])

            # Create history entry
            ScheduleStatusHistory.objects.create(
                schedule=schedule,
                status=new_status,
                notes=notes or f"Status changed from {old_status} to {new_status}",
                changed_by=user
            )

            return schedule

    @staticmethod
    def start_schedule(schedule, user=None):
        """
        Mark schedule as started.

        Args:
            schedule: Schedule instance
            user: User starting the schedule

        Returns:
            Updated Schedule instance
        """
        from django.utils import timezone

        from schedules.models import ScheduleStatus, ScheduleStatusHistory

        if schedule.status == ScheduleStatus.COMPLETED:
            raise ValidationError("Cannot start a completed schedule.")

        if schedule.status == ScheduleStatus.CANCELLED:
            raise ValidationError("Cannot start a cancelled schedule.")

        with transaction.atomic():
            schedule.status = ScheduleStatus.IN_PROGRESS
            schedule.actual_start_time = timezone.now()
            schedule.save(update_fields=['status', 'actual_start_time', 'updated_at'])

            # Create history entry
            ScheduleStatusHistory.objects.create(
                schedule=schedule,
                status=ScheduleStatus.IN_PROGRESS,
                notes="Schedule started",
                changed_by=user
            )

            return schedule

    @staticmethod
    def complete_schedule(schedule, user=None):
        """
        Mark schedule as completed.

        Args:
            schedule: Schedule instance
            user: User completing the schedule

        Returns:
            Updated Schedule instance
        """
        from django.utils import timezone

        from schedules.models import ScheduleStatus, ScheduleStatusHistory

        if schedule.status == ScheduleStatus.COMPLETED:
            raise ValidationError("Schedule is already completed.")

        if schedule.status == ScheduleStatus.CANCELLED:
            raise ValidationError("Cannot complete a cancelled schedule.")

        with transaction.atomic():
            schedule.status = ScheduleStatus.COMPLETED
            schedule.actual_end_time = timezone.now()
            schedule.completed_by = user
            schedule.save(update_fields=[
                'status', 'actual_end_time', 'completed_by', 'updated_at'
            ])

            # Create history entry
            ScheduleStatusHistory.objects.create(
                schedule=schedule,
                status=ScheduleStatus.COMPLETED,
                notes="Schedule completed",
                changed_by=user
            )

            return schedule

    @staticmethod
    def cancel_schedule(schedule, reason=None, user=None):
        """
        Cancel a schedule.

        Args:
            schedule: Schedule instance
            reason: Reason for cancellation
            user: User cancelling the schedule

        Returns:
            Updated Schedule instance
        """
        from schedules.models import ScheduleStatus, ScheduleStatusHistory

        if schedule.status == ScheduleStatus.COMPLETED:
            raise ValidationError("Cannot cancel a completed schedule.")

        if schedule.status == ScheduleStatus.CANCELLED:
            return schedule  # Already cancelled

        with transaction.atomic():
            schedule.status = ScheduleStatus.CANCELLED
            if reason:
                schedule.internal_notes = f"{schedule.internal_notes or ''}\n\nCancellation: {reason}".strip()
            schedule.save(update_fields=['status', 'internal_notes', 'updated_at'])

            # Create history entry
            ScheduleStatusHistory.objects.create(
                schedule=schedule,
                status=ScheduleStatus.CANCELLED,
                notes=reason or "Schedule cancelled",
                changed_by=user
            )

            return schedule

    @staticmethod
    def reschedule(schedule, new_date, new_time, technician=None, reason=None, user=None):
        """
        Reschedule an appointment to a new date/time.

        Args:
            schedule: Schedule instance
            new_date: New scheduled date
            new_time: New scheduled time
            technician: New technician (optional, keeps existing if not provided)
            reason: Reason for rescheduling
            user: User making the change

        Returns:
            Updated Schedule instance
        """
        from schedules.models import ScheduleStatus, ScheduleStatusHistory

        if schedule.status == ScheduleStatus.COMPLETED:
            raise ValidationError("Cannot reschedule a completed schedule.")

        if schedule.status == ScheduleStatus.CANCELLED:
            raise ValidationError("Cannot reschedule a cancelled schedule.")

        # Check new technician availability if provided
        if technician:
            available = get_available_technicians(
                new_date,
                new_time,
                schedule.estimated_duration
            )
            if technician not in available:
                raise ValidationError(
                    f"Technician {technician.get_full_name()} is not available at the requested time."
                )

        with transaction.atomic():
            old_date = schedule.scheduled_date
            old_time = schedule.scheduled_time
            old_tech = schedule.technician

            # Update schedule
            schedule.scheduled_date = new_date
            schedule.scheduled_time = new_time
            if technician:
                schedule.technician = technician
            schedule.status = ScheduleStatus.RESCHEDULED

            if reason:
                schedule.internal_notes = f"{schedule.internal_notes or ''}\n\nRescheduled: {reason}".strip()

            schedule.save(update_fields=[
                'scheduled_date', 'scheduled_time', 'technician',
                'status', 'internal_notes', 'updated_at'
            ])

            # Create history entry
            tech_change = f" and technician to {technician.get_full_name()}" if technician and technician != old_tech else ""
            ScheduleStatusHistory.objects.create(
                schedule=schedule,
                status=ScheduleStatus.RESCHEDULED,
                notes=f"Rescheduled from {old_date} {old_time} to {new_date} {new_time}{tech_change}. Reason: {reason or 'Not specified'}",
                changed_by=user
            )

            return schedule


class ScheduleConflictChecker:
    """Checks for scheduling conflicts."""

    @staticmethod
    def check_technician_conflict(technician, schedule_date, start_time,
                                  duration_minutes, exclude_schedule_id=None):
        """
        Check if a technician has a conflicting schedule.

        Args:
            technician: Technician user
            schedule_date: Date to check
            start_time: Start time to check
            duration_minutes: Duration in minutes
            exclude_schedule_id: Schedule ID to exclude from check (for updates)

        Returns:
            dict with conflict status and details
        """
        from schedules.models import Schedule, ScheduleStatus

        if not technician:
            return {'has_conflict': False}

        # Calculate end time
        end_time = (
            datetime.combine(date.today(), start_time) +
            timedelta(minutes=duration_minutes)
        ).time()

        # Find overlapping schedules
        conflicts = Schedule.objects.filter(
            technician=technician,
            scheduled_date=schedule_date,
            status__in=[
                ScheduleStatus.PENDING,
                ScheduleStatus.CONFIRMED,
                ScheduleStatus.IN_PROGRESS
            ]
        )

        if exclude_schedule_id:
            conflicts = conflicts.exclude(id=exclude_schedule_id)

        # Check for time overlap
        overlapping = []
        for schedule in conflicts:
            schedule_end = (
                datetime.combine(date.today(), schedule.scheduled_time) +
                timedelta(minutes=schedule.estimated_duration)
            ).time()

            # Check if times overlap
            if not (schedule_end <= start_time or schedule.scheduled_time >= end_time):
                overlapping.append(schedule)

        return {
            'has_conflict': len(overlapping) > 0,
            'conflicts': overlapping,
            'conflict_count': len(overlapping)
        }

    @staticmethod
    def get_available_time_slots(technician, schedule_date, duration_minutes=60,
                                 start_hour=8, end_hour=18):
        """
        Get available time slots for a technician on a given date.

        Args:
            technician: Technician user
            schedule_date: Date to check
            duration_minutes: Required duration
            start_hour: Start of work day (hour)
            end_hour: End of work day (hour)

        Returns:
            List of available time slots
        """
        # Generate potential time slots (every 30 minutes)
        available_slots = []
        current_time = time(start_hour, 0)
        end_time = time(end_hour, 0)

        while current_time < end_time:
            # Check if this slot conflicts
            conflict = ScheduleConflictChecker.check_technician_conflict(
                technician=technician,
                schedule_date=schedule_date,
                start_time=current_time,
                duration_minutes=duration_minutes
            )

            if not conflict['has_conflict']:
                available_slots.append(current_time)

            # Move to next slot (30 minute intervals)
            current_time = (
                datetime.combine(date.today(), current_time) +
                timedelta(minutes=30)
            ).time()

        return available_slots


# Convenience functions

def create_home_service_schedule(service, scheduled_date=None, scheduled_time=None,
                                 technician=None, user=None):
    """Create a home service schedule."""
    from schedules.models import ScheduleType
    return ScheduleManager.create_schedule_from_service(
        service=service,
        schedule_type=ScheduleType.HOME_SERVICE,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        technician=technician,
        user=user
    )


def create_pull_out_return_schedules(service, pull_out_date, pull_out_time,
                                     return_date, return_time,
                                     technician=None, user=None):
    """Create pull-out and return schedules."""
    return ScheduleManager.create_pull_out_return_schedules(
        service=service,
        pull_out_date=pull_out_date,
        pull_out_time=pull_out_time,
        return_date=return_date,
        return_time=return_time,
        technician=technician,
        user=user
    )


def check_availability(technician, schedule_date, start_time, duration_minutes=60):
    """Check if technician is available."""
    result = ScheduleConflictChecker.check_technician_conflict(
        technician=technician,
        schedule_date=schedule_date,
        start_time=start_time,
        duration_minutes=duration_minutes
    )
    return not result['has_conflict']


def get_technician_daily_schedule(technician, schedule_date):
    """
    Get all schedules for a technician on a specific date.

    Args:
        technician: Technician user
        schedule_date: Date to get schedule for

    Returns:
        QuerySet of Schedule instances ordered by time
    """
    from schedules.models import Schedule, ScheduleStatus

    return Schedule.objects.filter(
        technician=technician,
        scheduled_date=schedule_date
    ).exclude(
        status=ScheduleStatus.CANCELLED
    ).order_by('scheduled_time')
