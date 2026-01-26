from django_filters import rest_framework as filters
from schedules.models import Schedule


class ScheduleFilter(filters.FilterSet):
    """Filter class for Schedule model with date range and field filters"""

    # Date range filters
    scheduled_date = filters.DateFilter(field_name='scheduled_datetime__date', lookup_expr='exact')
    scheduled_date_after = filters.DateFilter(field_name='scheduled_datetime__date', lookup_expr='gte')
    scheduled_date_before = filters.DateFilter(field_name='scheduled_datetime__date', lookup_expr='lte')
    scheduled_datetime_after = filters.DateTimeFilter(field_name='scheduled_datetime', lookup_expr='gte')
    scheduled_datetime_before = filters.DateTimeFilter(field_name='scheduled_datetime', lookup_expr='lte')

    # Service type filter
    service_type = filters.ChoiceFilter(choices=Schedule.SERVICE_TYPES)

    # Client filter
    client = filters.NumberFilter(field_name='client__id')
    client_name = filters.CharFilter(field_name='client__full_name', lookup_expr='icontains')

    # Technician filter
    technician = filters.NumberFilter(field_name='technician__id')
    technician_name = filters.CharFilter(field_name='technician__first_name', lookup_expr='icontains')

    # Month and year filters for calendar views
    month = filters.NumberFilter(method='filter_by_month')
    year = filters.NumberFilter(method='filter_by_year')

    # Ordering
    ordering = filters.OrderingFilter(
        fields=(
            ('scheduled_datetime', 'scheduled_datetime'),
            ('created_at', 'created_at'),
            ('client__full_name', 'client_name'),
            ('service_type', 'service_type'),
        ),
    )

    class Meta:
        model = Schedule
        fields = [
            'service_type',
            'client',
            'technician',
            'scheduled_date',
            'scheduled_date_after',
            'scheduled_date_before',
        ]

    def filter_by_month(self, queryset, name, value):
        """Filter schedules by month (1-12)"""
        if value and 1 <= value <= 12:
            return queryset.filter(scheduled_datetime__month=value)
        return queryset

    def filter_by_year(self, queryset, name, value):
        """Filter schedules by year"""
        if value:
            return queryset.filter(scheduled_datetime__year=value)
        return queryset
