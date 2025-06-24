from django.urls import path
from users.api import views

name = "users"

urlpatterns = [
    path("", views.UserListView.as_view(), name="user-list"),
    path("<int:pk>/", views.AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("profile/", views.MyProfileView.as_view(), name="my-profile"),
]
