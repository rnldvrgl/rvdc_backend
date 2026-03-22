import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time notifications."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.accept()
            await self.close(code=4001)
            return

        self.group_name = f"notifications_{user.id}"
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        except Exception:
            logger.exception("Failed to join group %s", self.group_name)
            await self.accept()
            await self.close(code=4002)
            return

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            try:
                await self.channel_layer.group_discard(
                    self.group_name, self.channel_name
                )
            except Exception:
                logger.exception("Failed to leave group %s", self.group_name)

    async def send_notification(self, event):
        """Handle notification events sent to the group."""
        await self.send(text_data=json.dumps(event["data"]))
