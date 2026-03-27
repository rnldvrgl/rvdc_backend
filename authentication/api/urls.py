from django.urls import path
from authentication.api.views import (
    DeviceAwareTokenRefreshView,
    LoginView,
    LogoutView,
    RegisterView,
    SessionListView,
    SessionRevokeView,
    AdminSessionListView,
    AdminSessionRevokeView,
    VerifyAdminView,
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
)

app_name = "auth"


urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("register/", RegisterView.as_view(), name="register"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", DeviceAwareTokenRefreshView.as_view(), name="token_refresh"),
    path("verify-admin/", VerifyAdminView.as_view(), name="verify_admin"),
    path("sessions/", SessionListView.as_view(), name="session_list"),
    path("sessions/<int:session_id>/revoke/", SessionRevokeView.as_view(), name="session_revoke"),
    path("admin/sessions/", AdminSessionListView.as_view(), name="admin_session_list"),
    path("admin/sessions/<int:session_id>/revoke/", AdminSessionRevokeView.as_view(), name="admin_session_revoke"),
]
