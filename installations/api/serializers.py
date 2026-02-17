from installations.models import (
    AirconBrand,
    AirconModel,
    AirconUnit,
    WarrantyClaim,
)
from rest_framework import serializers
from services.models import Service
from clients.api.serializers import ClientSerializer


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
    promo_price = serializers.ReadOnlyField()
    parts_warranty_years = serializers.ReadOnlyField()
    labor_warranty_years = serializers.ReadOnlyField()

    class Meta:
        model = AirconModel
        fields = [
            "id",
            "brand",
            "brand_id",
            "name",
            "retail_price",
            "aircon_type",
            "horsepower",
            "discount_percentage",
            "is_inverter",
            "has_discount",
            "promo_price",
            "parts_warranty_months",
            "labor_warranty_months",
            "parts_warranty_years",
            "labor_warranty_years",
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
        source="model", queryset=AirconModel.objects.all(), write_only=True, required=True
    )
    reserved_by = ClientSerializer(read_only=True)
    stall_name = serializers.CharField(source="stall.name", read_only=True)
    warranty_end_date = serializers.ReadOnlyField()
    warranty_status = serializers.ReadOnlyField()
    warranty_days_left = serializers.ReadOnlyField()
    is_reserved = serializers.ReadOnlyField()
    is_available_for_sale = serializers.ReadOnlyField()
    unit_status = serializers.ReadOnlyField()
    sale_price = serializers.ReadOnlyField()
    # Per-type warranty fields
    parts_warranty_end_date = serializers.ReadOnlyField()
    labor_warranty_end_date = serializers.ReadOnlyField()
    parts_warranty_days_left = serializers.ReadOnlyField()
    labor_warranty_days_left = serializers.ReadOnlyField()
    parts_warranty_status = serializers.ReadOnlyField()
    labor_warranty_status = serializers.ReadOnlyField()
    free_cleaning_status = serializers.ReadOnlyField()
    free_cleaning_redemption_date = serializers.ReadOnlyField()
    free_cleaning_service_id = serializers.ReadOnlyField()
    client_name = serializers.SerializerMethodField()
    sold_date = serializers.SerializerMethodField()
    installed_date = serializers.SerializerMethodField()

    class Meta:
        model = AirconUnit
        fields = [
            "id",
            "model",
            "model_id",
            "serial_number",
            "outdoor_serial_number",
            "stall",
            "stall_name",
            "sale",
            "installation_service",
            "reserved_by",
            "reserved_at",
            "warranty_start_date",
            "warranty_period_months",
            "free_cleaning_redeemed",
            "free_cleaning_service",
            "is_sold",
            "warranty_end_date",
            "warranty_status",
            "warranty_days_left",
            "parts_warranty_end_date",
            "labor_warranty_end_date",
            "parts_warranty_days_left",
            "labor_warranty_days_left",
            "parts_warranty_status",
            "labor_warranty_status",
            "free_cleaning_status",
            "free_cleaning_redemption_date",
            "free_cleaning_service_id",
            "is_reserved",
            "is_available_for_sale",
            "unit_status",
            "sale_price",
            "client_name",
            "sold_date",
            "installed_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "stall", 
            "is_sold", 
            "sale_price", 
            "reserved_by", 
            "reserved_at", 
            "sale", 
            "installation_service", 
            "warranty_start_date",
            "free_cleaning_redeemed",
            "free_cleaning_service",
        ]
    
    def get_client_name(self, obj):
        """Get client name from sale or reservation."""
        if obj.sale and obj.sale.client:
            return obj.sale.client.full_name
        if obj.reserved_by:
            return obj.reserved_by.full_name
        return None

    def get_sold_date(self, obj):
        """Get sold date from the sale transaction."""
        if obj.sale and obj.sale.created_at:
            return obj.sale.created_at.date().isoformat()
        return None

    def get_installed_date(self, obj):
        """Get installation completion date from the installation service."""
        if obj.installation_service and obj.installation_service.status == "completed":
            return obj.installation_service.updated_at.date().isoformat()
        return None

    def validate_serial_number(self, value):
        """Ensure indoor serial number is unique and uppercase"""
        value = value.upper()
        
        # Check for uniqueness, excluding current instance if updating
        qs = AirconUnit.objects.filter(serial_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        
        if qs.exists():
            raise serializers.ValidationError("A unit with this indoor serial number already exists.")
        
        return value
    
    def validate_outdoor_serial_number(self, value):
        """Ensure outdoor serial number is unique and uppercase if provided"""
        if not value:
            return value
            
        value = value.upper()
        
        # Check for uniqueness, excluding current instance if updating
        qs = AirconUnit.objects.filter(outdoor_serial_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        
        if qs.exists():
            raise serializers.ValidationError("A unit with this outdoor serial number already exists.")
        
        return value
    
    def create(self, validated_data):
        """Create unit with automatic stall assignment based on user role"""
        request = self.context.get('request')
        user = request.user if request else None
        
        # Auto-assign stall based on user role
        if user:
            if user.role in ['manager', 'clerk'] and user.assigned_stall:
                # For manager/clerk, use their assigned main stall
                from inventory.models import Stall
                main_stall = Stall.objects.filter(
                    stall_type='main',
                    is_system=True
                ).first()
                if main_stall:
                    validated_data['stall'] = main_stall
            elif user.role == 'admin':
                # For admin, use the main stall
                from inventory.models import Stall
                main_stall = Stall.objects.filter(
                    stall_type='main',
                    is_system=True
                ).first()
                if main_stall:
                    validated_data['stall'] = main_stall
        
        return super().create(validated_data)

    def validate_serial_number(self, value):
        if AirconUnit.objects.filter(serial_number__iexact=value).exists():
            raise serializers.ValidationError("This serial number is already in use.")
        return value

    def validate_free_cleaning_redeemed(self, value):
        """
        Allow toggling free_cleaning_redeemed only if the unit is installed.
        """
        instance = self.instance  # available when updating
        if value and instance and not instance.installation_service:
            raise serializers.ValidationError(
                "Cannot redeem free cleaning before the unit is installed."
            )
        return value


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
    Serializer for creating an installation service for an aircon unit.
    
    Workflow:
    - If unit not sold and sell_unit_now=False: Unit is RESERVED for the client
    - If unit not sold and sell_unit_now=True: Unit is SOLD first, then installation scheduled
    - If unit already sold: Installation is scheduled directly
    
    Note: Units don't need to be sold before installation - they can be reserved.
    """

    unit_id = serializers.IntegerField(help_text="AirconUnit ID to install")
    client_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Client ID (required if unit not sold - will reserve unit for this client)"
    )
    scheduled_date = serializers.DateField(required=False, allow_null=True)
    scheduled_time = serializers.TimeField(required=False, allow_null=True)
    labor_fee = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Labor fee for installation"
    )
    labor_is_free = serializers.BooleanField(
        default=False,
        help_text="Mark labor as free (promotional)"
    )
    sell_unit_now = serializers.BooleanField(
        default=False,
        help_text="If True, sell the unit first (optional - units can be reserved without selling)"
    )
    payment_type = serializers.ChoiceField(
        choices=['cash', 'gcash', 'credit', 'debit', 'cheque'],
        default='cash',
        help_text="Payment method if selling unit now"
    )

    def validate_unit_id(self, value):
        """Validate unit exists."""
        from installations.models import AirconUnit

        try:
            unit = AirconUnit.objects.get(id=value)
        except AirconUnit.DoesNotExist:
            raise serializers.ValidationError("Unit not found.")

        if unit.installation_service:
            raise serializers.ValidationError("Unit already has an installation scheduled.")

        return value

    def validate(self, data):
        """Validate the complete installation request."""
        from installations.models import AirconUnit
        
        unit = AirconUnit.objects.get(id=data['unit_id'])
        
        # If selling unit now, it shouldn't already be sold
        if data.get('sell_unit_now') and unit.is_sold:
            raise serializers.ValidationError(
                {"sell_unit_now": "Unit is already sold. Set sell_unit_now to False."}
            )
        
        # If not selling, client_id is required to reserve the unit
        if not data.get('sell_unit_now') and not unit.is_sold and not data.get('client_id'):
            raise serializers.ValidationError(
                {"client_id": "Client ID is required to reserve unit for installation."}
            )
        
        return data

    def save(self):
        """Create installation service."""
        from clients.models import Client
        from installations.business_logic import AirconInstallationHandler
        from installations.models import AirconUnit

        unit_id = self.validated_data['unit_id']
        unit = AirconUnit.objects.get(id=unit_id)

        user = self.context.get('request').user if self.context.get('request') else None
        
        # Determine client
        if unit.is_sold and unit.sale:
            client = unit.sale.client
        else:
            # When selling unit now, client_id must be provided in context or validated_data
            client_id = self.validated_data.get('client_id') or self.context.get('client_id')
            if not client_id:
                raise serializers.ValidationError(
                    "client_id is required when creating installation for unsold unit."
                )
            client = Client.objects.get(id=client_id)

        result = AirconInstallationHandler.create_installation_service(
            unit=unit,
            client=client,
            scheduled_date=self.validated_data.get('scheduled_date'),
            scheduled_time=self.validated_data.get('scheduled_time'),
            labor_fee=self.validated_data.get('labor_fee'),
            labor_is_free=self.validated_data.get('labor_is_free', False),
            user=user,
            sell_unit_now=self.validated_data.get('sell_unit_now', False),
            payment_type=self.validated_data.get('payment_type', 'cash'),
        )

        return result


class AirconInstallationCompleteSerializer(serializers.Serializer):
    """Serializer for completing an aircon installation service."""

    completion_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Date of installation completion"
    )

    def save(self):
        """Complete the installation service."""
        from installations.business_logic import AirconInstallationHandler

        service = self.context.get('service')
        if not service:
            raise serializers.ValidationError("Service instance required in context.")

        user = self.context.get('request').user if self.context.get('request') else None

        result = AirconInstallationHandler.complete_installation(
            service=service,
            completion_date=self.validated_data.get('completion_date'),
            user=user
        )

        return result


# ============================================================================
# Warranty Management Serializers
# ============================================================================


class WarrantyClaimSerializer(serializers.ModelSerializer):
    """Serializer for warranty claims."""

    unit_serial_number = serializers.CharField(source='unit.serial_number', read_only=True)
    unit_model_name = serializers.CharField(source='unit.model.name', read_only=True)
    client_name = serializers.CharField(source='unit.sale.client.full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)
    service_id = serializers.IntegerField(source='service.id', read_only=True)

    # Computed fields
    is_pending = serializers.ReadOnlyField()
    is_approved = serializers.ReadOnlyField()
    warranty_days_remaining_at_claim = serializers.ReadOnlyField()

    class Meta:
        model = WarrantyClaim
        fields = [
            'id',
            'unit',
            'unit_serial_number',
            'unit_model_name',
            'client_name',
            'service',
            'service_id',
            'claim_type',
            'status',
            'issue_description',
            'customer_notes',
            'technician_assessment',
            'is_valid_claim',
            'reviewed_by',
            'reviewed_by_name',
            'reviewed_at',
            'rejection_reason',
            'estimated_cost',
            'actual_cost',
            'claim_date',
            'completed_at',
            'created_at',
            'updated_at',
            'is_pending',
            'is_approved',
            'warranty_days_remaining_at_claim',
        ]
        read_only_fields = [
            'status',
            'reviewed_by',
            'reviewed_at',
            'is_valid_claim',
            'rejection_reason',
            'completed_at',
        ]


class WarrantyClaimCreateSerializer(serializers.Serializer):
    """Serializer for creating a warranty claim."""

    unit_id = serializers.IntegerField(help_text="AirconUnit ID to create claim for")
    claim_type = serializers.ChoiceField(
        choices=WarrantyClaim.ClaimType.choices,
        default='repair',
        help_text="Type of warranty claim"
    )
    issue_description = serializers.CharField(
        max_length=5000,
        help_text="Description of the issue/defect"
    )
    customer_notes = serializers.CharField(
        max_length=5000,
        required=False,
        allow_blank=True,
        default='',
        help_text="Additional notes from customer"
    )

    def validate_unit_id(self, value):
        """Validate unit exists and is eligible for warranty."""
        from installations.business_logic import WarrantyEligibilityChecker
        from installations.models import AirconUnit

        try:
            unit = AirconUnit.objects.get(id=value)
        except AirconUnit.DoesNotExist:
            raise serializers.ValidationError("Unit not found.")

        # Check eligibility
        eligibility = WarrantyEligibilityChecker.check_eligibility(unit)
        if not eligibility['eligible']:
            raise serializers.ValidationError(
                f"Unit is not eligible for warranty claim: {eligibility['reason']}"
            )

        return value

    def save(self):
        """Create the warranty claim."""
        from installations.business_logic import WarrantyClaimManager
        from installations.models import AirconUnit

        unit_id = self.validated_data['unit_id']
        unit = AirconUnit.objects.get(id=unit_id)

        claim = WarrantyClaimManager.create_claim(
            unit=unit,
            issue_description=self.validated_data['issue_description'],
            claim_type=self.validated_data['claim_type'],
            customer_notes=self.validated_data.get('customer_notes', ''),
        )

        return claim


class WarrantyClaimApproveSerializer(serializers.Serializer):
    """Serializer for approving a warranty claim."""

    technician_assessment = serializers.CharField(
        max_length=5000,
        required=False,
        allow_blank=True,
        default='',
        help_text="Technician's assessment of the issue"
    )
    create_service = serializers.BooleanField(
        default=True,
        help_text="Automatically create a service for this claim"
    )
    scheduled_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Scheduled date for warranty service"
    )
    scheduled_time = serializers.TimeField(
        required=False,
        allow_null=True,
        help_text="Scheduled time for warranty service"
    )

    def save(self):
        """Approve the claim."""
        from installations.business_logic import WarrantyClaimManager

        claim = self.context.get('claim')
        if not claim:
            raise serializers.ValidationError("Claim instance required in context.")

        user = self.context.get('request').user if self.context.get('request') else None

        result = WarrantyClaimManager.approve_claim(
            claim=claim,
            reviewed_by=user,
            technician_assessment=self.validated_data.get('technician_assessment', ''),
            create_service=self.validated_data.get('create_service', True),
        )

        # Update service scheduling if provided
        if result.get('service') and (
            self.validated_data.get('scheduled_date') or self.validated_data.get('scheduled_time')
        ):
            service = result['service']
            if self.validated_data.get('scheduled_date'):
                service.scheduled_date = self.validated_data['scheduled_date']
            if self.validated_data.get('scheduled_time'):
                service.scheduled_time = self.validated_data['scheduled_time']
            service.save()

        return result


class WarrantyClaimRejectSerializer(serializers.Serializer):
    """Serializer for rejecting a warranty claim."""

    rejection_reason = serializers.CharField(
        max_length=5000,
        help_text="Reason for rejecting the claim"
    )
    is_valid_claim = serializers.BooleanField(
        default=False,
        help_text="Whether this was a valid claim (affects tracking)"
    )

    def validate_rejection_reason(self, value):
        """Ensure rejection reason is provided."""
        if not value or not value.strip():
            raise serializers.ValidationError("Rejection reason is required.")
        return value

    def save(self):
        """Reject the claim."""
        from installations.business_logic import WarrantyClaimManager

        claim = self.context.get('claim')
        if not claim:
            raise serializers.ValidationError("Claim instance required in context.")

        user = self.context.get('request').user if self.context.get('request') else None

        claim = WarrantyClaimManager.reject_claim(
            claim=claim,
            reviewed_by=user,
            rejection_reason=self.validated_data['rejection_reason'],
            is_valid_claim=self.validated_data.get('is_valid_claim', False),
        )

        return claim


class WarrantyClaimCancelSerializer(serializers.Serializer):
    """Serializer for cancelling a warranty claim."""

    cancellation_reason = serializers.CharField(
        max_length=5000,
        required=False,
        allow_blank=True,
        default='',
        help_text="Reason for cancellation"
    )

    def save(self):
        """Cancel the claim."""
        from installations.business_logic import WarrantyClaimManager

        claim = self.context.get('claim')
        if not claim:
            raise serializers.ValidationError("Claim instance required in context.")

        claim = WarrantyClaimManager.cancel_claim(
            claim=claim,
            cancellation_reason=self.validated_data.get('cancellation_reason', ''),
        )

        return claim


class FreeCleaningRedemptionSerializer(serializers.Serializer):
    """Serializer for redeeming free cleaning for an aircon unit."""

    unit_id = serializers.IntegerField(help_text="AirconUnit ID to redeem free cleaning for")
    scheduled_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Scheduled date for cleaning service"
    )
    scheduled_time = serializers.TimeField(
        required=False,
        allow_null=True,
        help_text="Scheduled time for cleaning service"
    )

    def validate_unit_id(self, value):
        """Validate unit exists and is eligible for free cleaning."""
        from installations.business_logic import FreeCleaningManager
        from installations.models import AirconUnit

        try:
            unit = AirconUnit.objects.get(id=value)
        except AirconUnit.DoesNotExist:
            raise serializers.ValidationError("Unit not found.")

        # Check eligibility
        eligibility = FreeCleaningManager.check_eligibility(unit)
        if not eligibility['eligible']:
            raise serializers.ValidationError(
                f"Unit is not eligible for free cleaning: {eligibility['reason']}"
            )

        return value

    def save(self):
        """Redeem free cleaning."""
        from installations.business_logic import FreeCleaningManager
        from installations.models import AirconUnit

        unit_id = self.validated_data['unit_id']
        unit = AirconUnit.objects.get(id=unit_id)

        result = FreeCleaningManager.redeem_free_cleaning(
            unit=unit,
            scheduled_date=self.validated_data.get('scheduled_date'),
            scheduled_time=self.validated_data.get('scheduled_time'),
        )

        return result


class FreeCleaningBatchRedemptionSerializer(serializers.Serializer):
    """Serializer for redeeming free cleaning for multiple aircon units under one client."""

    client_id = serializers.IntegerField(help_text="Client ID")
    unit_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="List of AirconUnit IDs to redeem free cleaning for"
    )
    scheduled_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Scheduled date for cleaning service"
    )
    scheduled_time = serializers.TimeField(
        required=False,
        allow_null=True,
        help_text="Scheduled time for cleaning service"
    )

    def validate_client_id(self, value):
        """Validate client exists."""
        from clients.models import Client

        try:
            Client.objects.get(id=value)
        except Client.DoesNotExist:
            raise serializers.ValidationError("Client not found.")
        return value

    def validate_unit_ids(self, value):
        """Validate all units exist."""
        from installations.models import AirconUnit

        units = AirconUnit.objects.filter(id__in=value).select_related(
            'model', 'model__brand', 'sale', 'sale__client'
        )
        if units.count() != len(value):
            found_ids = set(units.values_list('id', flat=True))
            missing = set(value) - found_ids
            raise serializers.ValidationError(f"Units not found: {missing}")
        return value

    def save(self):
        """Redeem free cleaning for multiple units."""
        from clients.models import Client
        from installations.business_logic import FreeCleaningManager
        from installations.models import AirconUnit

        client_id = self.validated_data['client_id']
        unit_ids = self.validated_data['unit_ids']
        client = Client.objects.get(id=client_id)
        units = list(AirconUnit.objects.filter(id__in=unit_ids).select_related(
            'model', 'model__brand', 'sale', 'sale__client'
        ))

        result = FreeCleaningManager.redeem_free_cleaning_batch(
            units=units,
            client=client,
            scheduled_date=self.validated_data.get('scheduled_date'),
            scheduled_time=self.validated_data.get('scheduled_time'),
        )

        return result


class WarrantyEligibilitySerializer(serializers.Serializer):
    """Serializer for checking warranty eligibility."""

    unit_id = serializers.IntegerField(help_text="AirconUnit ID to check")

    def validate_unit_id(self, value):
        """Validate unit exists."""
        from installations.models import AirconUnit

        try:
            AirconUnit.objects.get(id=value)
        except AirconUnit.DoesNotExist:
            raise serializers.ValidationError("Unit not found.")

        return value

    def check(self):
        """Check eligibility."""
        from installations.business_logic import WarrantyEligibilityChecker
        from installations.models import AirconUnit

        unit_id = self.validated_data['unit_id']
        unit = AirconUnit.objects.get(id=unit_id)

        return WarrantyEligibilityChecker.check_eligibility(unit)


class FreeCleaningEligibilitySerializer(serializers.Serializer):
    """Serializer for checking free cleaning eligibility."""

    unit_id = serializers.IntegerField(help_text="AirconUnit ID to check")

    def validate_unit_id(self, value):
        """Validate unit exists."""
        from installations.models import AirconUnit

        try:
            AirconUnit.objects.get(id=value)
        except AirconUnit.DoesNotExist:
            raise serializers.ValidationError("Unit not found.")

        return value

    def check(self):
        """Check eligibility."""
        from installations.business_logic import FreeCleaningManager
        from installations.models import AirconUnit

        unit_id = self.validated_data['unit_id']
        unit = AirconUnit.objects.get(id=unit_id)

        return FreeCleaningManager.check_eligibility(unit)
