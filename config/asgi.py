"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from notifications.routing import websocket_urlpatterns as notification_ws  # noqa: E402
from attendance.routing import websocket_urlpatterns as attendance_ws  # noqa: E402
from analytics.routing import websocket_urlpatterns as dashboard_ws  # noqa: E402
from notifications.middleware import JWTAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddleware(
            URLRouter(notification_ws + attendance_ws + dashboard_ws)
        ),
    }
)
