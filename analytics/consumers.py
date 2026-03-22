import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class DashboardConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time dashboard, sales, services, and inventory updates.

    All authenticated users join their role-based group so they receive
    relevant updates (stock changes, sales, service status, etc.).
    """

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.accept()
            await self.close(code=4001)
            return

        # Shared group for broadcasting service/sales/inventory changes
        self.group_name = "dashboard_updates"
        try:
            await self.channel_layer.group_add(
                self.group_name, self.channel_name
            )
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

    async def dashboard_event(self, event):
        """Forward dashboard events to the WebSocket client."""
        await self.send(text_data=json.dumps(event["data"]))
