from django.urls import path

from .views import ChatUsersView

urlpatterns = [
    path("users/", ChatUsersView.as_view(), name="chat-users"),
]
