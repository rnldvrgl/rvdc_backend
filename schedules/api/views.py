"""
API views for scheduling system.

Endpoints:
- Schedule CRUD operations
- Create schedules from services
- Create pull-out/return schedules
- Technician daily schedule view
- Status updates (start, complete, cancel, reschedule)
- Availability checking
"""

from datetime import datetime

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from schedules.api.serializers import (
    PullOutReturnScheduleSerializer,
    ScheduleCreateFromServiceSerializer,
    ScheduleRescheduleSerializer,
    ScheduleSerializer,
    ScheduleStatusHistorySerializer,
    ScheduleStatusUpdateSerializer,
    TechnicianAvailabilitySerializer,
)
from schedules.business_logic import (
    ScheduleConflictChecker,
    ScheduleManager,
    get_available_technicians,
    get_technician_daily_schedule,
)
from schedules.models import Schedule, ScheduleStatus
from users.models import CustomUser


class ScheduleViewSet(viewsets.ModelViewSet):
    """
    Schedule operations for technician appointments.

    Endpoints:
    - GET /schedules/ - List all schedules
    - POST /schedules/ - Create schedule
    - GET /schedules/{id}/ - Get schedule details
    - PUT/PATCH /schedules/{id}/ - Update schedule
    - DELETE /schedules/{id}/ - Delete schedule
    - POST /schedules/create-from-service/ - Create schedule from service
    - POST /schedules/create-pull-out-return/ - Create pull-out and return schedules
    - GET /schedules/technician-daily/{technician_id}/{date}/ - Get technician's daily schedule
    - POST /schedules/{id}/start/ - Start schedule
    - POST /schedules/{id}/complete/ - Complete schedule
    - POST /schedules/{id}/cancel/ - Cancel schedule
    - POST /schedules/{id}/reschedule/ - Reschedule appointment
    - POST /schedules/check-availability/ - Check technician availability
    - GET /schedules/available-technicians/ - Get available technicians
    """

    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Schedule.objects.all().select_related(
            "client",
            "technician",
            "service",
            "created_by",
            "completed_by",
        )

        # Filter by date range
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")

        if start_date:
            queryset = queryset.filter(scheduled_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(scheduled_date__lte=end_date)

        # Filter by technician
        technician_id = self.request.query_params.get("technician")
        if technician_id:
            queryset = queryset.filter(technician_id=technician_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by client
        client_id = self.request.query_params.get("client")
        if client_id:
            queryset = queryset.filter(client_id=client_id)

        # Filter by service
        service_id = self.request.query_params.get("service")
        if service_id:
            queryset = queryset.filter(service_id=service_id)

        return queryset

    @action(detail=False, methods=["post"], url_path="create-from-service")
    def create_from_service(self, request):
        """
        Create a schedule from a service.

        Request body:
        {
            "service_id": 123,
            "schedule_type": "home_service",
            "scheduled_date": "2024-01-15",
            "scheduled_time": "14:00:00",
            "technician_id": 5,
            "estimated_duration": 60,
            "notes": "Additional notes"
        }
        """
        serializer = ScheduleCreateFromServiceSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        schedule = serializer.save()

        return Response(
            ScheduleSerializer(schedule).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["post"], url_path="create-pull-out-return")
    def create_pull_out_return(self, request):
        """
        Create both pull-out and return schedules for a pull_out_return service.

        Request body:
        {
            "service_id": 123,
            "pull_out_date": "2024-01-15",
            "pull_out_time": "09:00:00",
            "return_date": "2024-01-17",
            "return_time": "14:00:00",
            "technician_id": 5
        }

        Response:
        {
            "pull_out": {...},
            "return": {...}
        }
        """
        serializer = PullOutReturnScheduleSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(
            {
                "pull_out": ScheduleSerializer(result["pull_out"]).data,
                "return": ScheduleSerializer(result["return"]).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="technician-daily/(?P<technician_id>[^/.]+)/(?P<date>[^/.]+)",
    )
    def technician_daily_schedule(self, request, technician_id=None, date=None):
        """
        Get a technician's schedule for a specific day.

        URL: /schedules/technician-daily/{technician_id}/{date}/

        Response:
        {
            "technician_id": 5,
            "technician_name": "John Doe",
            "date": "2024-01-15",
            "schedules": [...],
            "total_count": 3,
            "total_duration": 180
        }
        """
        try:
            technician = CustomUser.objects.get(
                id=technician_id, role="technician", is_active=True
            )
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "Technician not found"}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            schedule_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        schedules = get_technician_daily_schedule(technician, schedule_date)

        total_duration = sum(s.estimated_duration for s in schedules)

        return Response(
            {
                "technician_id": technician.id,
                "technician_name": technician.get_full_name(),
                "date": str(schedule_date),
                "schedules": ScheduleSerializer(schedules, many=True).data,
                "total_count": schedules.count(),
                "total_duration_minutes": total_duration,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="start")
    def start_schedule(self, request, pk=None):
        """
        Mark schedule as started.

        Response:
        {
            "id": 123,
            "status": "in_progress",
            "actual_start_time": "2024-01-15T14:05:00Z"
        }
        """
        schedule = self.get_object()

        try:
            updated_schedule = ScheduleManager.start_schedule(
                schedule=schedule, user=request.user
            )

            return Response(
                ScheduleSerializer(updated_schedule).data, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete_schedule(self, request, pk=None):
        """
        Mark schedule as completed.

        Response:
        {
            "id": 123,
            "status": "completed",
            "actual_start_time": "2024-01-15T14:05:00Z",
            "actual_end_time": "2024-01-15T15:15:00Z",
            "actual_duration_minutes": 70
        }
        """
        schedule = self.get_object()

        try:
            updated_schedule = ScheduleManager.complete_schedule(
                schedule=schedule, user=request.user
            )

            return Response(
                ScheduleSerializer(updated_schedule).data, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel_schedule(self, request, pk=None):
        """
        Cancel a schedule.

        Request body:
        {
            "reason": "Client cancelled"
        }

        Response:
        {
            "id": 123,
            "status": "cancelled"
        }
        """
        schedule = self.get_object()
        reason = request.data.get("reason", "")

        try:
            updated_schedule = ScheduleManager.cancel_schedule(
                schedule=schedule, reason=reason, user=request.user
            )

            return Response(
                ScheduleSerializer(updated_schedule).data, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request, pk=None):
        """
        Reschedule an appointment.

        Request body:
        {
            "new_date": "2024-01-16",
            "new_time": "15:00:00",
            "technician_id": 5,
            "reason": "Client requested change"
        }
        """
        schedule = self.get_object()

        serializer = ScheduleRescheduleSerializer(
            data=request.data, context={"schedule": schedule, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated_schedule = serializer.save()

        return Response(
            ScheduleSerializer(updated_schedule).data, status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"], url_path="update-status")
    def update_status(self, request, pk=None):
        """
        Update schedule status.

        Request body:
        {
            "status": "confirmed",
            "notes": "Client confirmed appointment"
        }
        """
        schedule = self.get_object()

        serializer = ScheduleStatusUpdateSerializer(
            data=request.data, context={"schedule": schedule, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated_schedule = serializer.save()

        return Response(
            ScheduleSerializer(updated_schedule).data, status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["get"], url_path="history")
    def status_history(self, request, pk=None):
        """
        Get status change history for a schedule.

        Response:
        [
            {
                "status": "confirmed",
                "notes": "Client confirmed",
                "changed_by": "John Doe",
                "changed_at": "2024-01-14T10:00:00Z"
            }
        ]
        """
        schedule = self.get_object()
        history = schedule.status_history.all()

        return Response(
            ScheduleStatusHistorySerializer(history, many=True).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="check-availability")
    def check_availability(self, request):
        """
        Check if a technician is available at a specific time.

        Request body:
        {
            "technician_id": 5,
            "schedule_date": "2024-01-15",
            "start_time": "14:00:00",
            "duration_minutes": 60
        }

        Response:
        {
            "is_available": true,
            "conflicts": []
        }
        or
        {
            "is_available": false,
            "conflicts": [
                {
                    "id": 123,
                    "scheduled_time": "13:30:00",
                    "estimated_duration": 90
                }
            ]
        }
        """
        serializer = TechnicianAvailabilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        technician = CustomUser.objects.get(id=serializer.validated_data["technician_id"])

        result = ScheduleConflictChecker.check_technician_conflict(
            technician=technician,
            schedule_date=serializer.validated_data["schedule_date"],
            start_time=serializer.validated_data["start_time"],
            duration_minutes=serializer.validated_data["duration_minutes"],
        )

        return Response(
            {
                "is_available": not result["has_conflict"],
                "conflicts": ScheduleSerializer(result.get("conflicts", []), many=True).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="available-technicians")
    def available_technicians(self, request):
        """
        Get list of available technicians for a time slot.

        Query params:
        - date: YYYY-MM-DD
        - time: HH:MM:SS
        - duration: minutes (default 60)

        Response:
        [
            {
                "id": 5,
                "name": "John Doe",
                "email": "john@example.com"
            }
        ]
        """
        date_str = request.query_params.get("date")
        time_str = request.query_params.get("time")
        duration = int(request.query_params.get("duration", 60))

        if not date_str or not time_str:
            return Response(
                {"error": "Both date and time are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            schedule_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            schedule_time = datetime.strptime(time_str, "%H:%M:%S").time()
        except ValueError:
            return Response(
                {"error": "Invalid date or time format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        available = get_available_technicians(schedule_date, schedule_time, duration)

        return Response(
            [
                {
                    "id": tech.id,
                    "name": tech.get_full_name(),
                    "email": tech.email,
                }
                for tech in available
            ],
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        """Get filter options for schedule list."""
        from utils.filters.options import get_client_options, get_user_options

        filters_config = {
            "technician": {"options": lambda: get_user_options(include_roles=["technician"])},
            "client": {"options": lambda: get_client_options(include_number=True)},
            "status": {
                "options": lambda: [
                    {"label": choice[1], "value": choice[0]}
                    for choice in ScheduleStatus.choices
                ]
            },
            "schedule_type": {
                "options": lambda: [
                    {"label": "Home Service", "value": "home_service"},
                    {"label": "Pull-Out", "value": "pull_out"},
                    {"label": "Return", "value": "return"},
                    {"label": "On-Site", "value": "on_site"},
                ]
            },
        }

        ordering_config = [
            {"label": "Date", "value": "scheduled_date"},
            {"label": "Time", "value": "scheduled_time"},
            {"label": "Status", "value": "status"},
        ]

        # Simple response for now
        return Response(
            {
                "filters": {
                    key: config["options"]() if callable(config["options"]) else config["options"]
                    for key, config in filters_config.items()
                },
                "ordering": ordering_config,
            },
            status=status.HTTP_200_OK,
        )
