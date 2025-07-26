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


def build_role_based_ordering(
    ordering_config: List[Dict[str, str]], user_role: str
) -> List[Dict[str, str]]:
    return [o for o in ordering_config if user_role not in o.get("exclude_for", [])]


def get_role_based_filter_response(
    request,
    filters_config: Dict[str, Dict[str, Any]],
    ordering_config: List[Dict[str, str]],
) -> Response:
    user_role = getattr(request.user, "role", None)
    filters = build_role_based_filters(filters_config, user_role)
    ordering_config = build_role_based_ordering(ordering_config, user_role)
    return Response(
        {
            "filters": filters,
            "ordering": ordering_config,
        }
    )
