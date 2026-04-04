from django.urls import path

from .views import ChatImageUploadView, ChatUsersView

urlpatterns = [
    path("users/", ChatUsersView.as_view(), name="chat-users"),
    path("upload-image/", ChatImageUploadView.as_view(), name="chat-upload-image"),
]
