from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ConversationViewSet, webhook_handler

router = DefaultRouter()
router.register(r"conversations", ConversationViewSet, basename="conversation")

urlpatterns = [
    path("webhook/", webhook_handler, name="webhook"),
] + router.urls
