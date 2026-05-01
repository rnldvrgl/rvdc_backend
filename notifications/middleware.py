import logging
from urllib.parse import parse_qs, unquote_plus

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()
logger = logging.getLogger(__name__)


@database_sync_to_async
def get_user(token_str):
    try:
        token = AccessToken(token_str)
        return User.objects.get(id=token["user_id"])
    except Exception:
        logger.exception("Failed to resolve websocket user from JWT")
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """Authenticate WebSocket connections using JWT from query string."""

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode("utf-8")
        params = parse_qs(query_string)
        token = params.get("token", [None])[0]

        if not token:
            headers = {
                key.decode("utf-8").lower(): value.decode("utf-8")
                for key, value in scope.get("headers", [])
            }
            auth_header = headers.get("authorization", "").strip()
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1].strip()

        if token:
            token = unquote_plus(token).strip()

        if token:
            scope["user"] = await get_user(token)
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
