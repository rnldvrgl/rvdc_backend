import json

import redis
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()

REDIS_URL = (
    settings.CHANNEL_LAYERS.get("default", {})
    .get("CONFIG", {})
    .get("hosts", ["redis://redis:6379/0"])[0]
)


class ChatUsersView(APIView):
    """
    GET /api/chat/users/
    Returns chat-eligible users with online status and unread counts.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role not in ("admin", "manager", "clerk"):
            return Response(
                {"detail": "Chat not available for your role."},
                status=status.HTTP_403_FORBIDDEN,
            )

        users = (
            User.objects.filter(
                is_active=True,
                is_deleted=False,
                role__in=["admin", "manager", "clerk"],
            )
            .exclude(pk=user.pk)
            .values("id", "first_name", "last_name", "role", "profile_image")
        )

        r = redis.from_url(REDIS_URL, decode_responses=True)
        online_ids = r.smembers("chat:online")
        online_set = {int(uid) for uid in online_ids}

        result = []
        for u in users:
            # Get unread count from this user
            unread_key = f"chat:unread:{user.pk}:{u['id']}"
            unread = int(r.get(unread_key) or 0)

            # Get last message preview
            lo, hi = sorted((user.pk, u["id"]))
            room_key = f"chat:{lo}_{hi}"
            last_msgs = r.zrevrange(room_key, 0, 0)
            last_message = None
            if last_msgs:
                last_message = json.loads(last_msgs[0])

            result.append(
                {
                    "id": u["id"],
                    "first_name": u["first_name"],
                    "last_name": u["last_name"],
                    "name": f"{u['first_name']} {u['last_name']}".strip(),
                    "role": u["role"],
                    "profile_image": u["profile_image"],
                    "is_online": u["id"] in online_set,
                    "unread_count": unread,
                    "last_message": last_message,
                }
            )

        # Sort: online first, then by unread desc, then name
        result.sort(key=lambda x: (-x["is_online"], -x["unread_count"], x["name"]))
        r.close()

        return Response(result)
