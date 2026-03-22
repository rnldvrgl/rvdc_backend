"""
Web Push notification sender.

Sends push notifications to all registered browser subscriptions for a user.
Stale subscriptions (410 Gone / 404) are automatically cleaned up.
"""

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def send_web_push(user_id: int, title: str, body: str, url: str = "/", tag: str = ""):
    """Send a Web Push notification to all subscriptions of a user.

    Args:
        user_id: Target user's PK.
        title: Notification title shown in the OS notification.
        body: Notification body text.
        url: URL to open on notification click (relative path).
        tag: Optional tag to collapse duplicate notifications.
    """
    vapid_private = getattr(settings, "VAPID_PRIVATE_KEY", "")
    vapid_public = getattr(settings, "VAPID_PUBLIC_KEY", "")
    vapid_email = getattr(settings, "VAPID_ADMIN_EMAIL", "")

    if not vapid_private or not vapid_public:
        return

    try:
        from pywebpush import WebPushException, webpush

        from notifications.models import PushSubscription
    except ImportError:
        logger.warning("pywebpush not installed – skipping web push")
        return

    subscriptions = PushSubscription.objects.filter(user_id=user_id)
    if not subscriptions.exists():
        return

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "tag": tag,
    })

    vapid_claims = {"sub": f"mailto:{vapid_email}"}
    stale_ids = []

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims=vapid_claims,
            )
        except WebPushException as e:
            status_code = getattr(e, "response", None)
            status_code = getattr(status_code, "status_code", None) if status_code else None
            if status_code in (404, 410):
                stale_ids.append(sub.id)
            else:
                logger.warning("WebPush failed for sub %s: %s", sub.id, e)
        except Exception:
            logger.exception("Unexpected error sending web push to sub %s", sub.id)

    if stale_ids:
        PushSubscription.objects.filter(id__in=stale_ids).delete()
