from typing import List, Dict, Any
from rest_framework.response import Response


def build_role_based_filters(
    filters_config: Dict[str, Dict[str, Any]],
    user_role: str,
) -> Dict[str, List[Dict[str, str]]]:
    filters = {}
    for key, config in filters_config.items():
        exclude_roles = config.get("exclude_for", [])
        if user_role not in exclude_roles:
            filters[key] = config["options"]()
    return filters


def get_role_based_filter_response(
    request,
    filters_config: Dict[str, Dict[str, Any]],
    ordering_config: List[Dict[str, str]],
) -> Response:
    user_role = getattr(request.user, "role", None)
    filters = build_role_based_filters(filters_config, user_role)
    return Response(
        {
            "filters": filters,
            "ordering": ordering_config,
        }
    )
