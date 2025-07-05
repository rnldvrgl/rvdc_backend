from rest_framework import generics, permissions
from utils.logger import log_activity


class LogCreateMixin:
    def perform_create(self, serializer):
        instance = serializer.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action=f"Created {instance.__class__.__name__}",
            note=f"{instance.__class__.__name__} created with ID {getattr(instance, 'id', 'N/A')}.",
        )


class LogUpdateMixin:
    def perform_update(self, serializer):
        instance = serializer.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action=f"Updated {instance.__class__.__name__}",
            note=f"{instance.__class__.__name__} updated with ID {getattr(instance, 'id', 'N/A')}.",
        )


class LogSoftDeleteMixin:
    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action=f"Deleted {instance.__class__.__name__}",
            note=f"{instance.__class__.__name__} marked as deleted with ID {getattr(instance, 'id', 'N/A')}.",
        )


class SimpleChoiceAPIView(generics.ListAPIView):
    pagination_class = None
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset
