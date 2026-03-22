import json
import logging
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = getattr(settings, "CHANNEL_LAYERS", {}).get(
    "default", {}
).get("CONFIG", {}).get("hosts", ["redis://redis:6379/0"])[0]

# Message TTL: 24 hours
MESSAGE_TTL = 60 * 60 * 24

# Maximum messages to keep per room
MAX_MESSAGES = 200


def _room_key(user_a: int, user_b: int) -> str:
    """Deterministic room key for a 1-on-1 conversation."""
    lo, hi = sorted((user_a, user_b))
    return f"chat:{lo}_{hi}"


def _presence_key() -> str:
    return "chat:online"


def _last_seen_key(user_id: int) -> str:
    return f"chat:last_seen:{user_id}"


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for ephemeral 1-on-1 chat.
    Messages stored in Redis sorted sets with 24h TTL — no database models.

    Client sends:
      { "action": "send", "to": <user_id>, "body": "<text>" }
      { "action": "history", "with": <user_id>, "before": <timestamp?> }
      { "action": "typing", "to": <user_id> }
      { "action": "read", "from": <user_id> }

    Server pushes:
      { "type": "message", "message": { id, from, to, body, ts } }
      { "type": "typing", "from": <user_id> }
      { "type": "read", "from": <user_id> }
      { "type": "history", "messages": [...], "with": <user_id> }
      { "type": "presence", "online": [<user_id>, ...] }
    """

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.accept()
            await self.close(code=4001)
            return

        self.user_id = self.user.id
        self.user_group = f"chat_user_{self.user_id}"

        try:
            self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            # Join personal group for incoming messages
            await self.channel_layer.group_add(self.user_group, self.channel_name)
            # Mark online
            await self._redis.sadd(_presence_key(), self.user_id)
            await self._redis.delete(_last_seen_key(self.user_id))
        except Exception:
            logger.exception("Chat connect failed for user %s", self.user_id)
            await self.accept()
            await self.close(code=4002)
            return

        await self.accept()

        # Broadcast updated presence to all connected users
        await self._broadcast_presence()

    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            try:
                await self.channel_layer.group_discard(
                    self.user_group, self.channel_name
                )
            except Exception:
                logger.exception("Failed to leave chat group")

        if hasattr(self, "_redis"):
            try:
                await self._redis.srem(_presence_key(), self.user_id)
                # Store last seen timestamp (7-day expiry)
                await self._redis.set(
                    _last_seen_key(self.user_id),
                    str(time.time()),
                    ex=60 * 60 * 24 * 7,
                )
                await self._broadcast_presence()
            except Exception:
                logger.exception("Failed to update presence on disconnect")
            finally:
                try:
                    await self._redis.aclose()
                except Exception:
                    pass

    # ── Inbound from client ──────────────────────────────────────────────

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            return

        action = payload.get("action")

        if action == "send":
            await self._handle_send(payload)
        elif action == "history":
            await self._handle_history(payload)
        elif action == "typing":
            await self._handle_typing(payload)
        elif action == "read":
            await self._handle_read(payload)
        elif action == "presence":
            await self._send_presence()

    # ── Actions ──────────────────────────────────────────────────────────

    async def _handle_send(self, payload):
        to_id = payload.get("to")
        body = (payload.get("body") or "").strip()
        if not to_id or not body or len(body) > 2000:
            return

        # Validate target user exists and is eligible for chat
        if not await self._is_chat_eligible(to_id):
            return

        ts = time.time()
        msg_id = f"{self.user_id}:{int(ts * 1000)}"

        message = {
            "id": msg_id,
            "from": self.user_id,
            "from_name": await self._get_display_name(self.user_id),
            "to": to_id,
            "body": body,
            "ts": ts,
        }

        room = _room_key(self.user_id, to_id)

        # Store in Redis sorted set (score = timestamp)
        await self._redis.zadd(room, {json.dumps(message): ts})
        await self._redis.expire(room, MESSAGE_TTL)

        # Trim to keep only the most recent messages
        await self._redis.zremrangebyrank(room, 0, -(MAX_MESSAGES + 1))

        # Store unread counter
        unread_key = f"chat:unread:{to_id}:{self.user_id}"
        await self._redis.incr(unread_key)
        await self._redis.expire(unread_key, MESSAGE_TTL)

        # Push to both sender and recipient
        event = {"type": "chat.message", "data": {"type": "message", "message": message}}
        await self.channel_layer.group_send(f"chat_user_{to_id}", event)
        await self.channel_layer.group_send(self.user_group, event)

    async def _handle_history(self, payload):
        with_id = payload.get("with")
        if not with_id:
            return

        room = _room_key(self.user_id, with_id)

        # Get all messages (max 100 most recent)
        raw = await self._redis.zrevrange(room, 0, 99)
        messages = [json.loads(m) for m in reversed(raw)]

        await self.send(text_data=json.dumps({
            "type": "history",
            "with": with_id,
            "messages": messages,
        }))

    async def _handle_typing(self, payload):
        to_id = payload.get("to")
        if not to_id:
            return
        await self.channel_layer.group_send(
            f"chat_user_{to_id}",
            {"type": "chat.typing", "data": {"type": "typing", "from": self.user_id}},
        )

    async def _handle_read(self, payload):
        from_id = payload.get("from")
        if not from_id:
            return

        # Clear unread counter
        unread_key = f"chat:unread:{self.user_id}:{from_id}"
        await self._redis.delete(unread_key)

        # Notify sender that messages were read
        await self.channel_layer.group_send(
            f"chat_user_{from_id}",
            {"type": "chat.read", "data": {"type": "read", "from": self.user_id}},
        )

    # ── Group event handlers ─────────────────────────────────────────────

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["data"]))

    async def chat_typing(self, event):
        await self.send(text_data=json.dumps(event["data"]))

    async def chat_read(self, event):
        await self.send(text_data=json.dumps(event["data"]))

    async def chat_presence(self, event):
        await self.send(text_data=json.dumps(event["data"]))

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _broadcast_presence(self):
        """Push online user list to all chat-connected users."""
        online_ids = await self._redis.smembers(_presence_key())
        online = [int(uid) for uid in online_ids]
        eligible = await self._get_chat_users()
        eligible_ids = {u["id"] for u in eligible}

        for uid in online:
            if uid in eligible_ids:
                await self.channel_layer.group_send(
                    f"chat_user_{uid}",
                    {
                        "type": "chat.presence",
                        "data": {"type": "presence", "online": online},
                    },
                )

    async def _send_presence(self):
        """Send presence list to the requesting client only."""
        online_ids = await self._redis.smembers(_presence_key())
        online = [int(uid) for uid in online_ids]
        await self.send(text_data=json.dumps({
            "type": "presence",
            "online": online,
        }))

    @database_sync_to_async
    def _is_chat_eligible(self, user_id):
        """Only admin, manager, clerk can chat."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            u = User.objects.get(pk=user_id, is_active=True, is_deleted=False)
            return u.role in ("admin", "manager", "clerk")
        except User.DoesNotExist:
            return False

    @database_sync_to_async
    def _get_display_name(self, user_id):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            u = User.objects.get(pk=user_id)
            return f"{u.first_name} {u.last_name}".strip() or u.username
        except User.DoesNotExist:
            return "Unknown"

    @database_sync_to_async
    def _get_chat_users(self):
        """Return all chat-eligible users."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        users = User.objects.filter(
            is_active=True, is_deleted=False,
            role__in=["admin", "manager", "clerk"],
        ).values("id", "first_name", "last_name", "role", "profile_image")
        return list(users)
