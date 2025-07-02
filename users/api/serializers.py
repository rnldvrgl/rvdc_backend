from rest_framework import serializers
from users.models import CustomUser
from inventory.api.serializers import StallSerializer
from drf_extra_fields.fields import Base64ImageField


class TechnicianSerializer(serializers.ModelSerializer):
    profile_image = Base64ImageField(required=False, allow_null=True)

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "birthday",
            "address",
            "province",
            "city",
            "barangay",
            "contact_number",
            "profile_image",
            "is_active",
            "sss_number",
            "philhealth_number",
            "basic_salary",
        ]
        read_only_fields = ("id",)


class UserSerializer(serializers.ModelSerializer):
    profile_image = Base64ImageField(required=False, allow_null=True)
    current_password = serializers.CharField(write_only=True, required=False)
    new_password = serializers.CharField(write_only=True, required=False)
    assigned_stall = StallSerializer(read_only=True)

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
            "current_password",
            "new_password",
            "sss_number",
            "philhealth_number",
            "basic_salary",
        ]
        read_only_fields = ("id",)

    def update(self, instance, validated_data):
        request = self.context.get("request")

        # protect staff removal
        if (
            request
            and request.user == instance
            and validated_data.get("is_staff") is False
        ):
            raise serializers.ValidationError(
                {"is_staff": "You cannot remove your own admin rights."}
            )

        # handle password change
        current_password = validated_data.pop("current_password", None)
        new_password = validated_data.pop("new_password", None)

        if new_password:
            if not current_password:
                raise serializers.ValidationError(
                    {
                        "current_password": "Current password is required to set a new password."
                    }
                )
            if not instance.check_password(current_password):
                raise serializers.ValidationError(
                    {"current_password": "Current password is incorrect."}
                )
            instance.set_password(new_password)

        if "profile_image" in validated_data and validated_data["profile_image"] == "":
            # set to default (or None to clear)
            validated_data["profile_image"] = "profile_images/default_image.jpg"

        return super().update(instance, validated_data)
