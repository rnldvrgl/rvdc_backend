from rest_framework.pagination import CursorPagination, PageNumberPagination


class CustomCursorPagination(CursorPagination):
    page_size = 10
    ordering = ("-created_at", "-id")

    def get_page_size(self, request):
        raw_limit = request.query_params.get("limit")
        if not raw_limit:
            return self.page_size

        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return self.page_size

        return max(1, min(limit, 1000))


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "limit"
    max_page_size = 1000


class HybridPagination(CustomPageNumberPagination):
    """Default page-number pagination with opt-in cursor pagination."""

    cursor_pagination_class = CustomCursorPagination

    def paginate_queryset(self, queryset, request, view=None):
        if request.query_params.get("pagination") == "cursor":
            self._cursor_pagination = self.cursor_pagination_class()
            return self._cursor_pagination.paginate_queryset(queryset, request, view)

        self._cursor_pagination = None
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        if getattr(self, "_cursor_pagination", None) is not None:
            return self._cursor_pagination.get_paginated_response(data)

        return super().get_paginated_response(data)
