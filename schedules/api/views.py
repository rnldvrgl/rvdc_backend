from datetime import datetime, timedelta

from django.db.models import Count
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from schedules.api.filters import ScheduleFilter
from schedules.api.serializers import (
    ScheduleCreateUpdateSerializer,
    ScheduleDetailSerializer,
    ScheduleListSerializer,
)
from schedules.models import Schedule
from users.models import CustomUser
from utils.filters.role_filters import get_role_based_filter_response


class ScheduleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Schedule model with CRUD operations and custom actions
    Supports multiple technicians per schedule
    """
    queryset = Schedule.objects.all().prefetch_related('technicians', 'client')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ScheduleFilter
    search_fields = [
        'client__full_name',
        'technicians__first_name',
        'technicians__last_name',
        'service_type',
        'notes',
    ]
    ordering_fields = [
        'scheduled_datetime',
        'created_at',
        'service_type',
    ]
    ordering = ['-scheduled_datetime']

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action in ['create', 'update', 'partial_update']:
            return ScheduleCreateUpdateSerializer
        elif self.action == 'retrieve':
            return ScheduleDetailSerializer
        return ScheduleListSerializer

    def get_queryset(self):
        """Filter queryset based on user role and query parameters"""
        queryset = super().get_queryset()
        user = self.request.user

        # Role-based filtering
        if user.role == 'technician':
            # Technicians can only see schedules where they are assigned
            queryset = queryset.filter(technicians=user)
        elif user.role in ['manager', 'clerk']:
            # Managers and clerks see all schedules (could be filtered by stall if needed)
            pass

        # Apply distinct to avoid duplicates from ManyToMany joins
        queryset = queryset.distinct()

        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        if start_date and end_date:
            try:
                start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                queryset = queryset.filter(
                    scheduled_datetime__date__gte=start.date(),
                    scheduled_datetime__date__lte=end.date()
                )
            except (ValueError, AttributeError):
                pass

        return queryset

    @action(detail=False, methods=['get'], url_path='filters')
    def get_filters(self, request):
        """Return available filter options for the frontend"""
        filters_config = {
            'service_type': {
                'options': lambda: [
                    {'label': display, 'value': value}
                    for value, display in Schedule.SERVICE_TYPES
                ],
            },
            'client': {
                'options': lambda: [
                    {
                        'label': schedule.client.full_name,
                        'value': schedule.client.id
                    }
                    for schedule in Schedule.objects.select_related('client')
                    .distinct('client')
                    .order_by('client__full_name')[:100]
                ],
            },
            'technician': {
                'options': lambda: [
                    {
                        'label': tech.get_full_name(),
                        'value': tech.id
                    }
                    for tech in CustomUser.objects.filter(
                        role='technician',
                        is_deleted=False
                    ).order_by('first_name', 'last_name')
                ],
            },
        }

        ordering_config = [
            {'label': 'Scheduled Date', 'value': 'scheduled_datetime'},
            {'label': 'Client Name', 'value': 'client__full_name'},
            {'label': 'Service Type', 'value': 'service_type'},
            {'label': 'Created Date', 'value': 'created_at'},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)

    @action(detail=False, methods=['get'], url_path='upcoming')
    def upcoming(self, request):
        """Get upcoming schedules (next 7 days)"""
        now = timezone.now()
        upcoming_date = now + timedelta(days=7)

        queryset = self.get_queryset().filter(
            scheduled_datetime__gte=now,
            scheduled_datetime__lte=upcoming_date
        ).order_by('scheduled_datetime')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='today')
    def today(self, request):
        """Get schedules for today"""
        today = timezone.now().date()

        queryset = self.get_queryset().filter(
            scheduled_datetime__date=today
        ).order_by('scheduled_datetime')

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-technician/(?P<technician_id>[0-9]+)')
    def by_technician(self, request, technician_id=None):
        """Get schedules for a specific technician"""
        queryset = self.get_queryset().filter(technicians__id=technician_id)

        # Apply date filters if provided
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            try:
                queryset = queryset.filter(scheduled_datetime__date__gte=start_date)
            except (ValueError, AttributeError):
                pass

        if end_date:
            try:
                queryset = queryset.filter(scheduled_datetime__date__lte=end_date)
            except (ValueError, AttributeError):
                pass

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-client/(?P<client_id>[0-9]+)')
    def by_client(self, request, client_id=None):
        """Get schedules for a specific client"""
        queryset = self.get_queryset().filter(client_id=client_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='unassigned')
    def unassigned(self, request):
        """Get schedules without any technicians assigned"""
        queryset = self.get_queryset().annotate(
            tech_count=Count('technicians')
        ).filter(tech_count=0)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='calendar')
    def calendar_view(self, request):
        """Get schedules formatted for calendar display"""
        queryset = self.get_queryset()

        # Get date range from query params
        start = request.query_params.get('start')
        end = request.query_params.get('end')

        if start and end:
            try:
                start_date = datetime.fromisoformat(start.replace('Z', '+00:00')).date()
                end_date = datetime.fromisoformat(end.replace('Z', '+00:00')).date()
                queryset = queryset.filter(
                    scheduled_datetime__date__gte=start_date,
                    scheduled_datetime__date__lte=end_date
                )
            except (ValueError, AttributeError):
                pass

        # Format for calendar
        events = []
        for schedule in queryset:
            # Get all technician names
            technician_names = [tech.get_full_name() for tech in schedule.technicians.all()]
            technician_ids = [tech.id for tech in schedule.technicians.all()]

            # Create title with technicians
            tech_display = ", ".join(technician_names) if technician_names else "Unassigned"

            events.append({
                'id': f'schedule-{schedule.id}',
                'title': f'{schedule.get_service_type_display()} - {schedule.client.full_name}',
                'start': schedule.scheduled_datetime.isoformat(),
                'allDay': False,
                'extendedProps': {
                    'type': 'schedule',
                    'schedule_id': schedule.id,
                    'service_type': schedule.service_type,
                    'client_name': schedule.client.full_name,
                    'client_id': schedule.client.id,
                    'technician_names': technician_names,
                    'technician_ids': technician_ids,
                    'technician_display': tech_display,
                    'technician_count': len(technician_names),
                    'notes': schedule.notes,
                }
            })

        return Response(events)

    @action(detail=False, methods=['get'], url_path='conflicts')
    def check_conflicts(self, request):
        """Check for scheduling conflicts for technicians at a specific time"""
        technician_ids = request.query_params.get('technician_ids')
        scheduled_datetime = request.query_params.get('scheduled_datetime')
        exclude_id = request.query_params.get('exclude_id')  # For updates

        if not technician_ids or not scheduled_datetime:
            return Response(
                {'error': 'technician_ids (comma-separated) and scheduled_datetime are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Parse technician IDs
            tech_ids = [int(tid.strip()) for tid in technician_ids.split(',')]
            scheduled_dt = datetime.fromisoformat(scheduled_datetime.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return Response(
                {'error': 'Invalid format for technician_ids or scheduled_datetime'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check for overlapping schedules (within 2 hours) for each technician
        time_buffer = timedelta(hours=2)
        start_time = scheduled_dt - time_buffer
        end_time = scheduled_dt + time_buffer

        all_conflicts = {}

        for tech_id in tech_ids:
            conflicting_schedules = Schedule.objects.filter(
                technicians__id=tech_id,
                scheduled_datetime__range=(start_time, end_time)
            ).select_related('client').distinct()

            # Exclude current schedule when updating
            if exclude_id:
                conflicting_schedules = conflicting_schedules.exclude(id=exclude_id)

            if conflicting_schedules.exists():
                technician = CustomUser.objects.get(id=tech_id)
                all_conflicts[tech_id] = {
                    'technician_name': technician.get_full_name(),
                    'conflicts': [
                        {
                            'id': schedule.id,
                            'client_name': schedule.client.full_name,
                            'scheduled_datetime': schedule.scheduled_datetime.isoformat(),
                            'service_type': schedule.service_type,
                        }
                        for schedule in conflicting_schedules
                    ]
                }

        has_conflicts = len(all_conflicts) > 0

        return Response({
            'has_conflicts': has_conflicts,
            'conflicts_by_technician': all_conflicts,
            'total_conflicts': sum(len(c['conflicts']) for c in all_conflicts.values())
        })

    @action(detail=False, methods=['get'], url_path='statistics')
    def statistics(self, request):
        """Get schedule statistics"""
        queryset = self.get_queryset()

        # Get date range
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date and end_date:
            try:
                queryset = queryset.filter(
                    scheduled_datetime__date__gte=start_date,
                    scheduled_datetime__date__lte=end_date
                )
            except (ValueError, AttributeError):
                pass

        # Count by service type
        service_counts = {}
        for service_type, display in Schedule.SERVICE_TYPES:
            count = queryset.filter(service_type=service_type).count()
            service_counts[service_type] = {
                'label': display,
                'count': count
            }

        # Count by technician
        technician_counts = {}
        technician_schedules = queryset.prefetch_related('technicians')
        for schedule in technician_schedules:
            for tech in schedule.technicians.all():
                tech_name = tech.get_full_name()
                if tech_name not in technician_counts:
                    technician_counts[tech_name] = 0
                technician_counts[tech_name] += 1

        # Count unassigned schedules
        unassigned_count = queryset.annotate(
            tech_count=Count('technicians')
        ).filter(tech_count=0).count()

        # Count upcoming vs past
        now = timezone.now()
        upcoming_count = queryset.filter(scheduled_datetime__gte=now).count()
        past_count = queryset.filter(scheduled_datetime__lt=now).count()

        return Response({
            'total': queryset.count(),
            'by_service_type': service_counts,
            'by_technician': technician_counts,
            'unassigned': unassigned_count,
            'upcoming': upcoming_count,
            'past': past_count,
        })

    @action(detail=True, methods=['post'], url_path='add-technician')
    def add_technician(self, request, pk=None):
        """Add a technician to an existing schedule"""
        schedule = self.get_object()
        technician_id = request.data.get('technician_id')

        if not technician_id:
            return Response(
                {'error': 'technician_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            technician = CustomUser.objects.get(
                id=technician_id,
                role='technician',
                is_deleted=False
            )
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'Technician not found or invalid'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if already assigned
        if schedule.technicians.filter(id=technician_id).exists():
            return Response(
                {'error': 'Technician already assigned to this schedule'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Add technician
        schedule.technicians.add(technician)

        serializer = self.get_serializer(schedule)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='remove-technician')
    def remove_technician(self, request, pk=None):
        """Remove a technician from a schedule"""
        schedule = self.get_object()
        technician_id = request.data.get('technician_id')

        if not technician_id:
            return Response(
                {'error': 'technician_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            technician = CustomUser.objects.get(id=technician_id)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'Technician not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Remove technician
        schedule.technicians.remove(technician)

        serializer = self.get_serializer(schedule)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Override to add custom logic when creating a schedule"""
        serializer.save()

    def perform_update(self, serializer):
        """Override to add custom logic when updating a schedule"""
        serializer.save()

    def perform_destroy(self, instance):
        """Override to use soft delete if needed, or just delete"""
        instance.delete()

