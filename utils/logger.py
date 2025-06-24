from django.contrib.contenttypes.models import ContentType
from logs.models import ActivityLog


def log_activity(user, instance, action: str, note: str = ""):
    ActivityLog.objects.create(
        content_type=ContentType.objects.get_for_model(instance),
        object_id=instance.id,
        action=action,
        note=note,
        performed_by=user,
    )
