from installations.models import (
    AirconBrand,
    AirconInstallation,
    AirconItemUsed,
    AirconModel,
    AirconUnit,
)
from rest_framework import serializers
from services.models import Service


class AirconBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirconBrand
        fields = ["id", "name"]

    def validate_name(self, value):
        if AirconBrand.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("This aircon brand already exists.")
        return value


class AirconModelSerializer(serializers.ModelSerializer):
    brand = AirconBrandSerializer(read_only=True)
    brand_id = serializers.PrimaryKeyRelatedField(
        source="brand", queryset=AirconBrand.objects.all(), write_only=True
    )
    has_discount = serializers.ReadOnlyField()

    class Meta:
        model = AirconModel
        fields = [
            "id",
            "brand",
            "brand_id",
            "name",
            "retail_price",
            "aircon_type",
            "discount_percentage",
            "is_inverter",
            "has_discount",
        ]

    def validate(self, data):
        brand = data.get("brand")
        name = data.get("name")

        # Exclude the current instance if updating
        qs = AirconModel.objects.filter(brand=brand, name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                f"Model '{name}' already exists under this brand."
            )
        return data


class AirconUnitSerializer(serializers.ModelSerializer):
    model = AirconModelSerializer(read_only=True)
    model_id = serializers.PrimaryKeyRelatedField(
        source="model", queryset=AirconModel.objects.all(), write_only=True
    )
    stall_name = serializers.CharField(source="stall.name", read_only=True)
    warranty_end_date = serializers.ReadOnlyField()
    warranty_status = serializers.ReadOnlyField()
    warranty_days_left = serializers.ReadOnlyField()
    is_reserved = serializers.ReadOnlyField()
    is_available_for_sale = serializers.ReadOnlyField()
    sale_price = serializers.ReadOnlyField()

    class Meta:
        model = AirconUnit
        fields = [
            "id",
            "model",
            "model_id",
            "serial_number",
            "stall",
            "stall_name",
            "sale",
            "installation",
            "reserved_by",
            "reserved_at",
            "warranty_start_date",
            "warranty_period_months",
            "free_cleaning_redeemed",
            "is_sold",
            "warranty_end_date",
            "warranty_status",
            "warranty_days_left",
            "is_reserved",
            "is_available_for_sale",
            "sale_price",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["stall", "is_sold", "sale_price"]

    def validate_serial_number(self, value):
        if AirconUnit.objects.filter(serial_number__iexact=value).exists():
            raise serializers.ValidationError("This serial number is already in use.")
        return value

    def validate_free_cleaning_redeemed(self, value):
        """
        Allow toggling free_cleaning_redeemed only if the unit is installed.
        """
        instance = self.instance  # available when updating
        if value and instance and not instance.installation:
            raise serializers.ValidationError(
                "Cannot redeem free cleaning before the unit is installed."
            )
        return value


class AirconItemUsedSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirconItemUsed
        fields = "__all__"


class AirconInstallationSerializer(serializers.ModelSerializer):
    service_id = serializers.PrimaryKeyRelatedField(
        source="service", queryset=Service.objects.all()
    )
    aircon_unit = AirconUnitSerializer(many=True, read_only=True)

    class Meta:
        model = AirconInstallation
        fields = "__all__"

    def validate(self, data):
        service = data.get("service")
        unit = data.get("unit", None)

        if (
            unit
            and AirconInstallation.objects.filter(service=service, unit=unit).exists()
        ):
            raise serializers.ValidationError(
                f"Aircon unit '{unit}' is already linked to this service."
            )
        return data


class AirconSaleSerializer(serializers.Serializer):
    """
    Serializer for selling aircon units.

    Handles single or multiple unit sales with payment processing.
    """

    unit_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="List of AirconUnit IDs to sell"
    )
    client_id = serializers.IntegerField(
        help_text="Client purchasing the units"
    )
    payment_type = serializers.ChoiceField(
        choices=['cash', 'gcash', 'credit', 'debit', 'cheque'],
        default='cash',
        help_text="Payment method"
    )

    def validate_unit_ids(self, value):
        """Validate that all units exist and are available."""
        from installations.models import AirconUnit

        if not value:
            raise serializers.ValidationError("At least one unit must be selected.")

        units = AirconUnit.objects.filter(id__in=value)

        if units.count() != len(value):
            raise serializers.ValidationError("Some units were not found.")

        # Check availability
        for unit in units:
            if not unit.is_available_for_sale:
                raise serializers.ValidationError(
                    f"Unit {unit.serial_number} is not available for sale."
                )

        return value

    def validate_client_id(self, value):
        """Validate client exists."""
        from clients.models import Client

        if not Client.objects.filter(id=value).exists():
            raise serializers.ValidationError("Client not found.")

        return value

    def save(self):
        """Execute the sale."""
        from clients.models import Client
        from installations.business_logic import AirconSalesHandler
        from installations.models import AirconUnit

        unit_ids = self.validated_data['unit_ids']
        client_id = self.validated_data['client_id']
        payment_type = self.validated_data['payment_type']

        client = Client.objects.get(id=client_id)
        units = AirconUnit.objects.filter(id__in=unit_ids)

        user = self.context.get('request').user if self.context.get('request') else None

        if len(units) == 1:
            # Single unit sale
            result = AirconSalesHandler.sell_unit(
                unit=units.first(),
                client=client,
                sales_clerk=user,
                payment_type=payment_type
            )
        else:
            # Multiple unit sale
            result = AirconSalesHandler.sell_multiple_units(
                units=list(units),
                client=client,
                sales_clerk=user,
                payment_type=payment_type
            )

        return result


class AirconReservationSerializer(serializers.Serializer):
    """Serializer for reserving aircon units."""

    unit_id = serializers.IntegerField(help_text="AirconUnit ID to reserve")
    client_id = serializers.IntegerField(help_text="Client reserving the unit")

    def validate_unit_id(self, value):
        """Validate unit exists and is available."""
        from installations.models import AirconUnit

        try:
            unit = AirconUnit.objects.get(id=value)
        except AirconUnit.DoesNotExist:
            raise serializers.ValidationError("Unit not found.")

        if not unit.is_available_for_sale:
            raise serializers.ValidationError("Unit is not available for reservation.")

        return value

    def validate_client_id(self, value):
        """Validate client exists."""
        from clients.models import Client

        if not Client.objects.filter(id=value).exists():
            raise serializers.ValidationError("Client not found.")

        return value

    def save(self):
        """Execute the reservation."""
        from clients.models import Client
        from installations.business_logic import AirconInventoryManager
        from installations.models import AirconUnit

        unit_id = self.validated_data['unit_id']
        client_id = self.validated_data['client_id']

        unit = AirconUnit.objects.get(id=unit_id)
        client = Client.objects.get(id=client_id)
        user = self.context.get('request').user if self.context.get('request') else None

        result = AirconInventoryManager.reserve_unit(unit, client, user)

        return result


class AirconInstallationCreateSerializer(serializers.Serializer):
    """
    Serializer for creating an installation service for a sold aircon unit.
    """

    unit_id = serializers.IntegerField(help_text="AirconUnit ID to install")
    scheduled_date = serializers.DateField(required=False, allow_null=True)
    scheduled_time = serializers.TimeField(required=False, allow_null=True)
    labor_fee = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Labor fee for installation"
    )
    apply_free_installation = serializers.BooleanField(
        default=False,
        help_text="Apply free installation promo"
    )
    copper_tube_length = serializers.IntegerField(
        default=0,
        help_text="Length of copper tube needed (ft)"
    )

    def validate_unit_id(self, value):
        """Validate unit exists and is sold."""
        from installations.models import AirconUnit

        try:
            unit = AirconUnit.objects.get(id=value)
        except AirconUnit.DoesNotExist:
            raise serializers.ValidationError("Unit not found.")

        if not unit.is_sold:
            raise serializers.ValidationError(
                "Unit must be sold before installation can be scheduled."
            )

        if unit.installation:
            raise serializers.ValidationError("Unit already has an installation scheduled.")

        return value

    def validate_copper_tube_length(self, value):
        """Validate copper tube length is non-negative."""
        if value < 0:
            raise serializers.ValidationError("Copper tube length cannot be negative.")
        return value

    def save(self):
        """Create installation service."""
        from installations.business_logic import AirconInstallationHandler
        from installations.models import AirconUnit

        unit_id = self.validated_data['unit_id']
        unit = AirconUnit.objects.get(id=unit_id)

        user = self.context.get('request').user if self.context.get('request') else None

        result = AirconInstallationHandler.create_installation_service(
            unit=unit,
            client=unit.sale.client if unit.sale else None,
            scheduled_date=self.validated_data.get('scheduled_date'),
            scheduled_time=self.validated_data.get('scheduled_time'),
            labor_fee=self.validated_data.get('labor_fee'),
            apply_free_installation=self.validated_data.get('apply_free_installation', False),
            copper_tube_length=self.validated_data.get('copper_tube_length', 0),
            user=user
        )

        return result


class AirconInstallationCompleteSerializer(serializers.Serializer):
    """Serializer for completing an aircon installation."""

    completion_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Date of installation completion"
    )

    def save(self):
        """Complete the installation."""
        from installations.business_logic import AirconInstallationHandler

        installation = self.context.get('installation')
        if not installation:
            raise serializers.ValidationError("Installation instance required in context.")

        user = self.context.get('request').user if self.context.get('request') else None

        result = AirconInstallationHandler.complete_installation(
            installation=installation,
            completion_date=self.validated_data.get('completion_date'),
            user=user
        )

        return result
