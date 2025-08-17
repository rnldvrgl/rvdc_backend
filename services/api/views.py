from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from utils.filters.role_filters import get_role_based_filter_response
from utils.query import filter_by_date_range
from utils.filters.options import (
    get_client_options,
    get_service_status_options,
    get_service_type_options,
    get_user_options,
)
from services.models import (
    Service,
    ServiceAppliance,
    ApplianceItemUsed,
    TechnicianAssignment,
)
from services.api.serializers import (
    ServiceSerializer,
    ServiceApplianceSerializer,
    ApplianceItemUsedSerializer,
    TechnicianAssignmentSerializer,
)


# --------------------------
# Service
# --------------------------
class ServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = (
            Service.objects.all()
            .select_related("client")
            .prefetch_related("appliances__items_used", "technician_assignments")
        )
        return filter_by_date_range(self.request, qs)

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "client": {"options": get_client_options(include_number=True)},
            "technician": {
                "options": lambda: get_user_options(include_roles=["technician"])
            },
            "status": {"options": get_service_status_options},
            "service_type": {"options": get_service_type_options},
        }

        ordering_config = [
            {"label": "Created At", "value": "created_at"},
            {"label": "Scheduled Date", "value": "scheduled_date"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)


# --------------------------
# Service Appliance
# --------------------------
class ServiceApplianceViewSet(viewsets.ModelViewSet):
    queryset = ServiceAppliance.objects.all().select_related(
        "service", "appliance_type"
    )
    serializer_class = ServiceApplianceSerializer
    permission_classes = [permissions.IsAuthenticated]


# --------------------------
# Appliance Items Used
# --------------------------
class ApplianceItemUsedViewSet(viewsets.ModelViewSet):
    queryset = ApplianceItemUsed.objects.all().select_related("appliance", "item")
    serializer_class = ApplianceItemUsedSerializer
    permission_classes = [permissions.IsAuthenticated]


# --------------------------
# Technician Assignment
# --------------------------
class TechnicianAssignmentViewSet(viewsets.ModelViewSet):
    queryset = TechnicianAssignment.objects.select_related("service", "technician")
    serializer_class = TechnicianAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="filters")
    def get_filters(self, request):
        filters_config = {
            "technician": {"options": get_user_options(include_roles=["technician"])},
            "status": {"options": get_service_status_options},
        }

        ordering_config = [
            {"label": "Service Date", "value": "service__scheduled_date"},
            {"label": "Created At", "value": "created_at"},
        ]

        return get_role_based_filter_response(request, filters_config, ordering_config)
