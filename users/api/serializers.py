from rest_framework import serializers
from users.models import CustomUser


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "birthday",
            "address",
            "contact_number",
            "profile_image",
            "is_active",
            "assigned_stall",
        ]
        read_only_fields = ("id",)

    def update(self, instance, validated_data):
        request = self.context.get("request")
        if (
            request
            and request.user == instance
            and validated_data.get("is_staff") is False
        ):
            raise serializers.ValidationError(
                {"is_staff": "You cannot remove your own admin rights."}
            )

        return super().update(instance, validated_data)
