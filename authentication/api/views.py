from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.views import TokenRefreshView
from authentication.api.serializers import (
    AuthSessionSerializer,
    DeviceAwareTokenRefreshSerializer,
    LoginSerializer,
    RegisterSerializer,
    LogoutSerializer,
)
from authentication.models import AuthSession
from authentication.session_tracking import revoke_session_by_id
from django.contrib.auth import authenticate


class LoginView(APIView):
    def post(self, request, format=None):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(data, status=status.HTTP_200_OK)


class RegisterView(APIView):
    def post(self, request, format=None):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return Response(data, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"detail": "Successfully logged out."},
                status=status.HTTP_205_RESET_CONTENT,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyAdminView(APIView):
    """Verify admin credentials for privileged operations (e.g. remittance override)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        if not username or not password:
            return Response(
                {"detail": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(username=username, password=password)

        if not user or user.role != "admin":
            return Response(
                {"detail": "Invalid admin credentials."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response({"detail": "Admin verified.", "admin_id": user.id})


class DeviceAwareTokenRefreshView(TokenRefreshView):
    serializer_class = DeviceAwareTokenRefreshSerializer


class SessionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        include_revoked = (
            str(request.query_params.get("include_revoked", "false")).lower()
            == "true"
        )

        sessions = AuthSession.objects.filter(user=request.user)
        if not include_revoked:
            sessions = sessions.filter(is_active=True)

        device_id = request.query_params.get("device_id") or request.headers.get(
            "X-Device-ID", ""
        )

        serializer = AuthSessionSerializer(
            sessions,
            many=True,
            context={"device_id": device_id},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class SessionRevokeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id: int):
        revoked = revoke_session_by_id(session_id=session_id, user=request.user)
        if not revoked:
            return Response(
                {"detail": "Session not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"detail": "Session revoked."}, status=status.HTTP_200_OK)
