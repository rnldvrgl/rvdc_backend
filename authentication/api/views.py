from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from authentication.api.serializers import (
    LoginSerializer,
    RegisterSerializer,
    LogoutSerializer,
)


class LoginView(APIView):
    def post(self, request, format=None):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(data, status=status.HTTP_200_OK)


class RegisterView(APIView):
    def post(self, request, format=None):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(data, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"detail": "Successfully logged out."},
                status=status.HTTP_205_RESET_CONTENT,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
