from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, PushSubscriptionView, VapidPublicKeyView

router = DefaultRouter()
router.register(r"", NotificationViewSet, basename="notification")
urlpatterns = [
    path("push/vapid-key/", VapidPublicKeyView.as_view(), name="vapid-public-key"),
    path("push/subscribe/", PushSubscriptionView.as_view(), name="push-subscribe"),
] + router.urls
