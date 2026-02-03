from django_filters import rest_framework as filters

from schedules.models import Schedule


class ScheduleFilter(filters.FilterSet):
    """Filter class for Schedule model with date range and field filters"""

    # Date range filters (updated to use scheduled_date instead of scheduled_datetime)
    scheduled_date = filters.DateFilter(field_name='scheduled_date', lookup_expr='exact')
    scheduled_date_after = filters.DateFilter(field_name='scheduled_date', lookup_expr='gte')
    scheduled_date_before = filters.DateFilter(field_name='scheduled_date', lookup_expr='lte')

    # Schedule type filter (updated from service_type)
    schedule_type = filters.ChoiceFilter(choices=Schedule.SCHEDULE_TYPES)

    # Status filter
    status = filters.ChoiceFilter(choices=Schedule.STATUS_CHOICES)

    # Service filter
    service = filters.NumberFilter(field_name='service__id')

    # Client filter
    client = filters.NumberFilter(field_name='client__id')
    client_name = filters.CharFilter(field_name='client__full_name', lookup_expr='icontains')

    # Technician filters (ManyToMany)
    technician = filters.NumberFilter(field_name='technicians__id')
    technician_name = filters.CharFilter(field_name='technicians__first_name', lookup_expr='icontains')
    has_technicians = filters.BooleanFilter(method='filter_has_technicians')

    # Month and year filters for calendar views
    month = filters.NumberFilter(method='filter_by_month')
    year = filters.NumberFilter(method='filter_by_year')

    # Ordering
    ordering = filters.OrderingFilter(
        fields=(
            ('scheduled_date', 'scheduled_date'),
            ('scheduled_time', 'scheduled_time'),
            ('created_at', 'created_at'),
            ('client__full_name', 'client_name'),
            ('schedule_type', 'schedule_type'),
            ('status', 'status'),
        ),
    )

    class Meta:
        model = Schedule
        fields = [
            'schedule_type',
            'status',
            'service',
            'client',
            'technician',
            'scheduled_date',
            'scheduled_date_after',
            'scheduled_date_before',
        ]

    def filter_by_month(self, queryset, name, value):
        """Filter schedules by month (1-12)"""
        if value and 1 <= value <= 12:
            return queryset.filter(scheduled_date__month=value)
        return queryset

    def filter_by_year(self, queryset, name, value):
        """Filter schedules by year"""
        if value:
            return queryset.filter(scheduled_date__year=value)
        return queryset

    def filter_has_technicians(self, queryset, name, value):
        """Filter schedules that have or don't have technicians assigned"""
        if value:
            return queryset.filter(technicians__isnull=False).distinct()
        else:
            return queryset.filter(technicians__isnull=True).distinct()
