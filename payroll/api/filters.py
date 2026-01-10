from django_filters import rest_framework as filters
from payroll.models import AdditionalEarning, Holiday, TimeEntry, WeeklyPayroll


class TimeEntryFilter(filters.FilterSet):
  """
  Filters for time entries:
  - start_date/end_date: range on clock_in date (inclusive start, exclusive end)
  - employee: by employee id
  - approved: boolean
  - source: one of TimeEntry.SOURCE_CHOICES
  - employee__assigned_stall: filter by employee's assigned stall id
  """
  start_date = filters.DateFilter(field_name="clock_in", lookup_expr="date__gte")
  end_date = filters.DateFilter(field_name="clock_in", lookup_expr="date__lt")
  employee = filters.NumberFilter(field_name="employee_id")
  approved = filters.BooleanFilter()
  source = filters.CharFilter(field_name="source")
  employee__assigned_stall = filters.NumberFilter(field_name="employee__assigned_stall_id")

  class Meta:
    model = TimeEntry
    fields = [
      "employee",
      "approved",
      "source",
      "employee__assigned_stall",
    ]


class AdditionalEarningFilter(filters.FilterSet):
  """
  Filters for additional earnings:
  - start_date/end_date: range on earning_date (inclusive start, exclusive end)
  - employee: by employee id
  - category: one of AdditionalEarning.EARNING_TYPES
  - approved: boolean
  - employee__assigned_stall: filter by employee's assigned stall id
  """
  start_date = filters.DateFilter(field_name="earning_date", lookup_expr="gte")
  end_date = filters.DateFilter(field_name="earning_date", lookup_expr="lt")
  employee = filters.NumberFilter(field_name="employee_id")
  category = filters.CharFilter(field_name="category")
  approved = filters.BooleanFilter()
  employee__assigned_stall = filters.NumberFilter(field_name="employee__assigned_stall_id")

  class Meta:
    model = AdditionalEarning
    fields = [
      "employee",
      "category",
      "approved",
      "employee__assigned_stall",
    ]



class WeeklyPayrollFilter(filters.FilterSet):

  """

  Filters for weekly payrolls:

  - start_date/end_date: overlap-aware range on the weekly period [week_start, week_start+7)
    Overlap condition: week_start < end_date AND (week_start + 7 days) > start_date
  - employee: by employee id

  - status: draft/approved/paid

  - employee__assigned_stall: filter by employee's assigned stall id

  """

  start_date = filters.DateFilter(method="filter_start_date")
  end_date = filters.DateFilter(method="filter_end_date")
  employee = filters.NumberFilter(field_name="employee_id")

  status = filters.CharFilter(field_name="status")

  employee__assigned_stall = filters.NumberFilter(field_name="employee__assigned_stall_id")



  class Meta:

    model = WeeklyPayroll

    fields = [

      "employee",

      "status",

      "week_start",

      "employee__assigned_stall",

    ]

  def filter_start_date(self, queryset, name, value):
    # include weeks whose end is after start_date -> week_start + 7 > start_date
    from datetime import timedelta
    return queryset.filter(week_start__gt=value - timedelta(days=7))

  def filter_end_date(self, queryset, name, value):
    # include weeks whose start is before end_date -> week_start < end_date
    return queryset.filter(week_start__lt=value)

class HolidayFilter(filters.FilterSet):

    class Meta:
        model = Holiday
        fields = [
        "kind"
        ]
