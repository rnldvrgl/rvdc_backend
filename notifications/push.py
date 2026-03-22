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
        logger.warning("[WebPush] VAPID keys not configured – skipping")
        return

    try:
        from pywebpush import WebPushException, webpush

        from notifications.models import PushSubscription
    except ImportError:
        logger.warning("[WebPush] pywebpush not installed – skipping")
        return

    subscriptions = PushSubscription.objects.filter(user_id=user_id)
    count = subscriptions.count()
    if count == 0:
        logger.info("[WebPush] No subscriptions for user %s – skipping", user_id)
        return

    logger.info("[WebPush] Sending to %d subscription(s) for user %s: %s", count, user_id, title)

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
                vapid_claims={**vapid_claims},
                content_encoding="aes128gcm",
            )
            logger.info("[WebPush] Sent OK to sub %s (endpoint: %s…)", sub.id, sub.endpoint[:60])
        except WebPushException as e:
            resp = getattr(e, "response", None)
            status_code = getattr(resp, "status_code", None) if resp else None
            resp_body = ""
            if resp is not None:
                try:
                    resp_body = resp.text
                except Exception:
                    resp_body = str(resp.content) if hasattr(resp, "content") else ""
            logger.warning(
                "[WebPush] Failed for sub %s: status=%s body=%s err=%s",
                sub.id, status_code, resp_body, e,
            )
            if status_code in (400, 404, 410):
                stale_ids.append(sub.id)
        except Exception:
            logger.exception("[WebPush] Unexpected error sending to sub %s", sub.id)

    if stale_ids:
        PushSubscription.objects.filter(id__in=stale_ids).delete()
