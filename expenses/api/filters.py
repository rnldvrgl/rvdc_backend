from django_filters import rest_framework as filters
from expenses.models import Expense


class ExpenseFilter(filters.FilterSet):
    is_paid = filters.BooleanFilter(method="filter_is_paid")

    class Meta:
        model = Expense
        fields = ["stall", "source", "is_paid"]

    def filter_is_paid(self, queryset, name, value):
        if value:
            return queryset.filter(is_paid=True)
        return queryset.filter(is_paid=False)
