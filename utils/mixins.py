from utils.logger import log_activity


class LogCreateMixin:
    def perform_create(self, serializer):
        instance = serializer.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action=f"Created {instance.__class__.__name__}",
            note=f"{instance.__class__.__name__} created.",
        )


class LogUpdateMixin:
    def perform_update(self, serializer):
        instance = serializer.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action=f"Updated {instance.__class__.__name__}",
            note=f"{instance.__class__.__name__} updated.",
        )


class LogSoftDeleteMixin:
    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()
        log_activity(
            user=self.request.user,
            instance=instance,
            action=f"Deleted {instance.__class__.__name__}",
            note=f"{instance.__class__.__name__} marked as deleted.",
        )
