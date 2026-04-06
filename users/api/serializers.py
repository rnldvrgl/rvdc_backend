from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from users.models import CustomUser, SystemSettings, CashAdvanceMovement
from inventory.api.serializers import StallSerializer
from drf_extra_fields.fields import Base64ImageField


class EmployeesSerializer(serializers.ModelSerializer):
    profile_image = Base64ImageField(required=False, allow_null=True)
    e_signature = Base64ImageField(required=False, allow_null=True)
    username = serializers.CharField(required=False, allow_blank=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "gender",
            "birthday",
            "address",
            "province",
            "city",
            "barangay",
            "contact_number",
            "profile_image",
            "e_signature",
            "is_active",
            "sss_number",
            "philhealth_number",
            "basic_salary",
            "cash_ban_balance",
            "include_in_payroll",
            "has_sss",
            "has_philhealth",
            "has_pagibig",
            "has_bir_tax",
            "has_cash_ban",
        ]
        read_only_fields = ("id", "cash_ban_balance")

    def get_full_name(self, obj):
        return obj.get_full_name()

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get("request")
        # Build absolute URLs for image fields
        for field_name in ("profile_image", "e_signature"):
            image = getattr(instance, field_name, None)
            if image and request:
                rep[field_name] = request.build_absolute_uri(image.url)
            elif image:
                rep[field_name] = image.url
            else:
                rep[field_name] = None
        return rep

    def validate_role(self, value):
        """Only allow manager, clerk, and technician roles for employees"""
        allowed_roles = ['manager', 'clerk', 'technician']
        if value not in allowed_roles:
            raise serializers.ValidationError(
                f"Invalid role. Only {', '.join(allowed_roles)} are allowed for employees."
            )
        return value

    def create(self, validated_data):
        """
        Auto-generate username from name initials if not provided, and set default password.
        Example: Ronald Vergel Dela Cruz -> username: rvdc, password: rvdc12
        """
        first_name = validated_data.get("first_name", "")
        last_name = validated_data.get("last_name", "")
        username = validated_data.get("username", "").strip()

        # If username not provided or empty, generate from initials
        if not username:
            # Generate username from initials
            # Split last name by spaces to get all parts
            name_parts = last_name.lower().split()
            # Get first letter of first name and all first letters from last name parts
            username_base = first_name[0].lower() if first_name else ""
            for part in name_parts:
                if part:
                    username_base += part[0]

            # Make sure username is unique by adding numbers if needed
            username = username_base
            counter = 1
            while CustomUser.objects.filter(username=username).exists():
                username = f"{username_base}{counter}"
                counter += 1
        else:
            # If username provided, check if it's unique
            if CustomUser.objects.filter(username=username).exists():
                raise serializers.ValidationError(
                    {"username": "This username is already taken. Please choose another one."}
                )

        validated_data["username"] = username

        # Set default password: rvdc12
        user = CustomUser(**validated_data)
        user.set_password("rvdc12")

        try:
            user.save()
        except DjangoValidationError as e:
            # Convert Django ValidationError to DRF ValidationError
            raise serializers.ValidationError({"role": e.messages})

        return user


class UserSerializer(serializers.ModelSerializer):
    profile_image = Base64ImageField(required=False, allow_null=True)
    e_signature = Base64ImageField(required=False, allow_null=True)
    current_password = serializers.CharField(write_only=True, required=False)
    new_password = serializers.CharField(write_only=True, required=False)
    assigned_stall = StallSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "gender",
            "birthday",
            "address",
            "contact_number",
            "profile_image",
            "e_signature",
            "is_active",
            "assigned_stall",
            "current_password",
            "new_password",
            "sss_number",
            "philhealth_number",
            "basic_salary",
            "cash_ban_balance",
            "include_in_payroll",
            "has_sss",
            "has_philhealth",
            "has_pagibig",
            "has_bir_tax",
            "has_cash_ban",
        ]
        read_only_fields = ("id", "cash_ban_balance")

    def get_full_name(self, obj):
        return obj.get_full_name()

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get("request")
        for field_name in ("profile_image", "e_signature"):
            image = getattr(instance, field_name, None)
            if image and request:
                rep[field_name] = request.build_absolute_uri(image.url)
            elif image:
                rep[field_name] = image.url
            else:
                rep[field_name] = None
        return rep

    def update(self, instance, validated_data):
        request = self.context.get("request")

        # protect staff removal
        if (
            request
            and request.user == instance
            and validated_data.get("is_staff") is False
        ):
            raise serializers.ValidationError(
                {"non_field_errors": ["You cannot remove your own admin rights."]}
            )

        # handle password change
        current_password = validated_data.pop("current_password", None)
        new_password = validated_data.pop("new_password", None)

        if new_password:
            if not current_password:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Current password is required to set a new password."
                        ]
                    }
                )
            if not instance.check_password(current_password):
                raise serializers.ValidationError(
                    {"non_field_errors": ["Current password is incorrect."]}
                )

            if new_password == current_password:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "New password cannot be the same as the current password."
                        ]
                    }
                )
            instance.set_password(new_password)

        if "profile_image" in validated_data and validated_data["profile_image"] == "":
            validated_data["profile_image"] = None

        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as e:
            # Convert Django ValidationError to DRF ValidationError
            raise serializers.ValidationError({"role": e.messages})


class SystemSettingsSerializer(serializers.ModelSerializer):
    """Serializer for system-wide settings"""

    class Meta:
        model = SystemSettings
        fields = [
            'id',
            'birthday_greeting_enabled',
            'birthday_greeting_title',
            'birthday_greeting_message',
            'birthday_greeting_button_text',
            'birthday_greeting_show_confetti',
            'birthday_greeting_show_emojis',
            'birthday_greeting_male_emojis',
            'birthday_greeting_female_emojis',
            'birthday_greeting_variant',
            'maintenance_mode',
            'check_stock_on_sale',
            'updated_at',
        ]
        read_only_fields = ['id', 'updated_at']


class CashAdvanceMovementSerializer(serializers.ModelSerializer):
    """Serializer for cash ban balance movements (credits and debits)"""

    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, default='')
    remaining_balance = serializers.DecimalField(
        source='employee.cash_ban_balance',
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = CashAdvanceMovement
        fields = [
            'id',
            'employee',
            'employee_name',
            'movement_type',
            'amount',
            'balance_after',
            'date',
            'description',
            'reference',
            'is_pending',
            'created_by',
            'created_by_name',
            'remaining_balance',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'balance_after', 'created_at', 'updated_at', 'created_by']

    def validate(self, data):
        employee = data.get('employee')
        amount = data.get('amount')
        movement_type = data.get('movement_type')
        is_pending = data.get('is_pending', False)

        if amount is not None and amount <= 0:
            raise serializers.ValidationError({
                'amount': 'Amount must be greater than zero.'
            })

        # Only validate balance for debits (cash advances) that are not pending
        # Pending movements (linked to draft payrolls) will be validated when applied
        if movement_type == CashAdvanceMovement.MovementType.DEBIT and amount and employee and not is_pending:
            if amount > employee.cash_ban_balance:
                raise serializers.ValidationError({
                    'amount': f'Insufficient cash ban balance. Available: ₱{employee.cash_ban_balance}'
                })

        return data

    def create(self, validated_data):
        """Set created_by from request user"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)
