from django.urls import path
from users.api import views

name = "users"

urlpatterns = [
    path("", views.UserListView.as_view(), name="user-list"),
    path("<int:pk>/", views.AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("profile/", views.MyProfileView.as_view(), name="my-profile"),
    path("technicians/", views.TechnicianListView.as_view(), name="technician-list"),
    path(
        "technicians/<int:pk>/",
        views.TechnicianDetailView.as_view(),
        name="technician-detail",
    ),
    path(
        "choices/technicians/",
        views.TechnicianChoicesAPIView.as_view(),
        name="technician-choices",
    ),
]
