"""
Web Push notification sender.

Sends push notifications to all registered browser subscriptions for a user.
Stale subscriptions (410 Gone / 404 / 400) are automatically cleaned up.
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)


def _extract_status_code(exc):
    """Extract HTTP status code from a WebPushException."""
    # Try response attribute first
    resp = getattr(exc, "response", None)
    if resp is not None:
        code = getattr(resp, "status_code", None)
        if code is not None:
            return code
    # Fall back to parsing the error message string (e.g. "Push failed: 400 Bad Request")
    match = re.search(r"(\d{3})", str(exc))
    return int(match.group(1)) if match else None


def send_web_push(user_id: int, title: str, body: str, url: str = "/", tag: str = "", extra_data: dict | None = None):
    """Send a Web Push notification to all subscriptions of a user."""
    vapid_private = getattr(settings, "VAPID_PRIVATE_KEY", "")
    vapid_email = getattr(settings, "VAPID_ADMIN_EMAIL", "")

    if not vapid_private:
        logger.warning("[WebPush] VAPID_PRIVATE_KEY not configured – skipping")
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
        **(extra_data or {}),
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
                ttl=86400,
            )
            logger.info("[WebPush] Sent OK to sub %s", sub.id)
        except WebPushException as e:
            status_code = _extract_status_code(e)
            logger.warning("[WebPush] Failed for sub %s: status=%s err=%s", sub.id, status_code, e)
            # Only delete subscriptions that are truly gone (unsubscribed/expired)
            # Do NOT delete on 400/401 — those are VAPID config issues, not dead subs
            if status_code in (404, 410):
                stale_ids.append(sub.id)
        except Exception:
            logger.exception("[WebPush] Unexpected error sending to sub %s", sub.id)

    if stale_ids:
        deleted, _ = PushSubscription.objects.filter(id__in=stale_ids).delete()
        logger.info("[WebPush] Cleaned up %d stale subscription(s)", deleted)
