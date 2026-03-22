"""Shared utility for pushing events to the dashboard WebSocket group."""

import logging

logger = logging.getLogger(__name__)


def push_dashboard_event(event_type: str, data: dict):
    """Push an event to all connected dashboard WebSocket clients."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return

        async_to_sync(channel_layer.group_send)(
            "dashboard_updates",
            {
                "type": "dashboard_event",
                "data": {"event": event_type, **data},
            },
        )
    except Exception:
        logger.exception("Failed to push dashboard event via WebSocket")
