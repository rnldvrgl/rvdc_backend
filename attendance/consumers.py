import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class AttendanceConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time attendance updates.

    Managers/admins join the shared 'attendance_updates' group to see
    live clock-in/out, approvals, leave changes, etc.
    Every authenticated user also joins their personal group so they
    receive updates about their own attendance (approvals, rejections).
    """

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.accept()
            await self.close(code=4001)
            return

        # Personal group – every user gets their own attendance events
        self.personal_group = f"attendance_user_{user.id}"
        try:
            await self.channel_layer.group_add(
                self.personal_group, self.channel_name
            )

            # Shared management group – admin/manager see all attendance events
            if user.role in ("admin", "manager"):
                self.management_group = "attendance_updates"
                await self.channel_layer.group_add(
                    self.management_group, self.channel_name
                )
        except Exception:
            logger.exception("Failed to join attendance groups")
            await self.accept()
            await self.close(code=4002)
            return

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "personal_group"):
            try:
                await self.channel_layer.group_discard(
                    self.personal_group, self.channel_name
                )
            except Exception:
                logger.exception("Failed to leave personal group")
        if hasattr(self, "management_group"):
            try:
                await self.channel_layer.group_discard(
                    self.management_group, self.channel_name
                )
            except Exception:
                logger.exception("Failed to leave management group")

    async def attendance_event(self, event):
        """Forward attendance events to the WebSocket client."""
        await self.send(text_data=json.dumps(event["data"]))
