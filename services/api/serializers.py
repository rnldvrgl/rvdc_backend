"""
Service API serializers with two-stall architecture support.

Features:
- Stock reservation on service creation
- Stock consumption on service completion
- Revenue attribution (Main vs Sub stall)
- Promo support (free installation, copper tube promos)
"""

from decimal import Decimal

from django.db import transaction
from inventory.models import Stock
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from services.business_logic import (
    PromoManager,
    RevenueCalculator,
    StockReservationManager,
    get_main_stall,
    get_sub_stall,
)
from services.models import (
    ApplianceItemUsed,
    Service,
    ServiceAppliance,
    TechnicianAssignment,
)


class ApplianceItemUsedSerializer(serializers.ModelSerializer):
    """
    Serializer for parts used in service appliances.

    Uses reservation flow:
    - On CREATE: Reserve stock (increment reserved_quantity)
    - On service COMPLETION: Consume stock (decrement quantity & reserved_quantity)
    - On service CANCELLATION: Release reservation (decrement reserved_quantity)
    """

    stall_stock_id = serializers.PrimaryKeyRelatedField(
        queryset=Stock.objects.all(),
        source="stall_stock",
        write_only=True,
        required=False,
        help_text="Optional: if omitted, system auto-resolves Sub stall stock for the item.",
    )

    item_name = serializers.CharField(source="item.name", read_only=True)
    item_price = serializers.DecimalField(
        source="item.retail_price", read_only=True, max_digits=10, decimal_places=2
    )

    # Promo fields
    apply_copper_tube_promo = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
        help_text="Apply free 10ft copper tube promo"
    )

    # Read-only fields
    free_quantity = serializers.IntegerField(read_only=True)
    promo_name = serializers.CharField(read_only=True)
    charged_quantity = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = ApplianceItemUsed
        fields = [
            "id",
            "appliance",
            "item",
            "item_name",
            "item_price",
            "quantity",
            "stall_stock_id",
            "is_free",
            "free_quantity",
            "promo_name",
            "charged_quantity",
            "line_total",
            "apply_copper_tube_promo",
        ]
        read_only_fields = ["free_quantity", "promo_name"]

    def get_charged_quantity(self, obj):
        """Quantity that will be charged (total - free)."""
        if obj.is_free:
            return 0
        return obj.quantity - obj.free_quantity

    def get_line_total(self, obj):
        """Total price for this line item."""
        if obj.is_free or not obj.item:
            return Decimal('0.00')

        charged_qty = obj.quantity - obj.free_quantity
        return obj.item.retail_price * charged_qty

    def validate(self, data):
        """Validate stock availability for reservation."""
        item = data.get("item")
        qty = data.get("quantity", 1)

        # Resolve stock
        stock = data.get("stall_stock")
        if stock is None:
            # Auto-resolve to Sub stall stock
            sub_stall = get_sub_stall()
            if not sub_stall:
                raise ValidationError("Sub stall not configured in system.")

            stock = Stock.objects.filter(
                item=item,
                stall=sub_stall,
                is_deleted=False
            ).first()

            if stock is None:
                raise ValidationError(f"No stock found for {item.name} in Sub stall.")

            data["stall_stock"] = stock

        # Validate stock belongs to correct item
        if stock.item != item:
            raise ValidationError("Selected stock does not match the item.")

        # Check available quantity (for reservation)
        available = stock.quantity - stock.reserved_quantity
        if qty > available:
            raise ValidationError(
                f"Insufficient stock for {item.name}. "
                f"Available: {available}, Requested: {qty}"
            )

        # Store validated stock for use in create()
        self._validated_stock = stock

        return data

    def create(self, validated_data):
        """
        Create item usage record and RESERVE stock (don't consume yet).
        Stock is consumed later when service is completed.
        """
        # Extract write-only fields
        apply_copper_promo = validated_data.pop("apply_copper_tube_promo", False)
        stock = self._validated_stock
        qty = validated_data.get("quantity", 1)
        is_free = validated_data.get("is_free", False)

        with transaction.atomic():
            # Reserve stock (increment reserved_quantity)
            reserved_stock = StockReservationManager.reserve_stock(
                item=validated_data["item"],
                quantity=qty,
                stall_stock=stock
            )

            # Create ApplianceItemUsed record
            validated_data["stall_stock"] = reserved_stock
            aiu = super().create(validated_data)

            # Apply promos if requested
            if apply_copper_promo and not is_free:
                free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(aiu)
                if applied:
                    aiu.save(update_fields=["free_quantity", "promo_name"])

            # Note: We do NOT create SalesTransaction or Expense here.
            # That happens on service completion via ServiceCompletionHandler.

        return aiu

    def update(self, instance, validated_data):
        """
        Update item usage and adjust reservation.

        Note: This only handles reservation adjustment.
        If service is already completed, this should be blocked at the view level.
        """
        apply_copper_promo = validated_data.pop("apply_copper_tube_promo", False)
        stock = self._validated_stock
        old_qty = instance.quantity
        new_qty = validated_data.get("quantity", old_qty)
        diff = new_qty - old_qty

        with transaction.atomic():
            # Adjust reservation
            if diff > 0:
                # Need to reserve more
                StockReservationManager.reserve_stock(
                    item=instance.item,
                    quantity=diff,
                    stall_stock=stock
                )
            elif diff < 0:
                # Release some reservation
                StockReservationManager.release_reservation(
                    item=instance.item,
                    quantity=abs(diff),
                    stall_stock=stock
                )

            # Update the instance
            instance = super().update(instance, validated_data)

            # Re-apply copper promo if requested
            if apply_copper_promo and not instance.is_free:
                free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(instance)
                if applied:
                    instance.save(update_fields=["free_quantity", "promo_name"])

        return instance


class TechnicianAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for technician assignments."""

    technician_name = serializers.CharField(source="technician.get_full_name", read_only=True)

    class Meta:
        model = TechnicianAssignment
        fields = [
            "id",
            "service",
            "appliance",
            "technician",
            "technician_name",
            "assignment_type",
            "note",
        ]


class ServiceApplianceSerializer(serializers.ModelSerializer):
    """Serializer for service appliances with promo support."""

    items_used = ApplianceItemUsedSerializer(many=True, required=False)
    technician_assignments = TechnicianAssignmentSerializer(many=True, required=False, read_only=True)

    # Promo fields
    apply_free_installation = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
        help_text="Apply free installation promo (sets labor_fee to 0)"
    )

    # Read-only computed fields
    appliance_type_name = serializers.CharField(
        source="appliance_type.name",
        read_only=True
    )
    total_parts_cost = serializers.SerializerMethodField()

    class Meta:
        model = ServiceAppliance
        fields = [
            "id",
            "service",
            "appliance_type",
            "appliance_type_name",
            "brand",
            "model",
            "issue_reported",
            "diagnosis_notes",
            "status",
            "labor_fee",
            "labor_is_free",
            "labor_original_amount",
            "apply_free_installation",
            "items_used",
            "technician_assignments",
            "total_parts_cost",
        ]
        read_only_fields = ["labor_original_amount"]

    def get_total_parts_cost(self, obj):
        """Calculate total cost of parts (excluding free items/quantities)."""
        total = Decimal('0.00')
        for item_used in obj.items_used.all():
            if item_used.is_free or not item_used.item:
                continue
            charged_qty = item_used.quantity - item_used.free_quantity
            total += item_used.item.retail_price * charged_qty
        return total

    def create(self, validated_data):
        """Create appliance with items and apply promos."""
        items_data = validated_data.pop("items_used", [])
        apply_free_install = validated_data.pop("apply_free_installation", False)

        with transaction.atomic():
            appliance = ServiceAppliance.objects.create(**validated_data)

            # Apply free installation promo if requested
            if apply_free_install:
                PromoManager.apply_free_installation(appliance)
                appliance.save(update_fields=["labor_fee", "labor_is_free", "labor_original_amount"])

            # Create items used (reserves stock)
            for item_data in items_data:
                item_data["appliance"] = appliance
                serializer = ApplianceItemUsedSerializer(
                    data=item_data,
                    context=self.context
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()

        return appliance

    def update(self, instance, validated_data):
        """Update appliance and items."""
        items_data = validated_data.pop("items_used", None)
        apply_free_install = validated_data.pop("apply_free_installation", False)

        with transaction.atomic():
            # Update appliance fields
            instance = super().update(instance, validated_data)

            # Apply/remove free installation promo
            if apply_free_install and not instance.labor_is_free:
                PromoManager.apply_free_installation(instance)
                instance.save(update_fields=["labor_fee", "labor_is_free", "labor_original_amount"])

            # Handle items update if provided
            if items_data is not None:
                # Release all existing reservations
                for old_item in instance.items_used.all():
                    if old_item.stall_stock:
                        StockReservationManager.release_reservation(
                            item=old_item.item,
                            quantity=old_item.quantity,
                            stall_stock=old_item.stall_stock
                        )
                    old_item.delete()

                # Create new items (reserves new stock)
                for item_data in items_data:
                    item_data["appliance"] = instance
                    serializer = ApplianceItemUsedSerializer(
                        data=item_data,
                        context=self.context
                    )
                    serializer.is_valid(raise_exception=True)
                    serializer.save()

        return instance


class ServiceSerializer(serializers.ModelSerializer):
    """
    Service serializer with two-stall architecture support.

    Handles:
    - Service creation with stock reservation
    - Revenue calculation and attribution
    - Service completion workflow
    """

    appliances = ServiceApplianceSerializer(many=True, required=False)
    technician_assignments = TechnicianAssignmentSerializer(many=True, required=False, read_only=True)

    # Read-only fields
    client_name = serializers.CharField(source="client.name", read_only=True)
    stall_name = serializers.CharField(source="stall.name", read_only=True)
    main_stall_revenue = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    sub_stall_revenue = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    total_revenue = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = Service
        fields = [
            "id",
            "client",
            "client_name",
            "stall",
            "stall_name",
            "service_type",
            "service_mode",
            "related_transaction",
            "description",
            "override_address",
            "override_contact_person",
            "override_contact_number",
            "scheduled_date",
            "scheduled_time",
            "estimated_duration",
            "pickup_date",
            "delivery_date",
            "status",
            "remarks",
            "notes",
            "created_at",
            "updated_at",
            "main_stall_revenue",
            "sub_stall_revenue",
            "total_revenue",
            "appliances",
            "technician_assignments",
        ]
        read_only_fields = [
            "main_stall_revenue",
            "sub_stall_revenue",
            "total_revenue",
            "created_at",
            "updated_at",
        ]

    def validate(self, data):
        """Validate service data."""
        # Auto-assign Main stall if not provided
        if "stall" not in data or data.get("stall") is None:
            main_stall = get_main_stall()
            if not main_stall:
                raise ValidationError("Main stall not configured in system.")
            data["stall"] = main_stall

        return data

    def create(self, validated_data):
        """
        Create service with appliances and reserve stock.
        Revenue is calculated but transactions are created on completion.
        """
        appliances_data = validated_data.pop("appliances", [])

        with transaction.atomic():
            service = Service.objects.create(**validated_data)

            # Create appliances (which reserves stock)
            for appliance_data in appliances_data:
                appliance_data["service"] = service
                serializer = ServiceApplianceSerializer(
                    data=appliance_data,
                    context=self.context
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()

            # Calculate initial revenue (no transactions yet)
            RevenueCalculator.calculate_service_revenue(service, save=True)

        return service

    def update(self, instance, validated_data):
        """Update service and appliances."""
        appliances_data = validated_data.pop("appliances", None)

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            # Handle appliances update if provided
            if appliances_data is not None:
                for appliance_data in appliances_data:
                    appliance_id = appliance_data.get("id")
                    if appliance_id:
                        # Update existing appliance
                        appliance = ServiceAppliance.objects.get(
                            id=appliance_id,
                            service=instance
                        )
                        serializer = ServiceApplianceSerializer(
                            appliance,
                            data=appliance_data,
                            partial=True,
                            context=self.context
                        )
                        serializer.is_valid(raise_exception=True)
                        serializer.save()
                    else:
                        # Create new appliance
                        appliance_data["service"] = instance
                        serializer = ServiceApplianceSerializer(
                            data=appliance_data,
                            context=self.context
                        )
                        serializer.is_valid(raise_exception=True)
                        serializer.save()

            # Recalculate revenue
            RevenueCalculator.calculate_service_revenue(instance, save=True)

        return instance


class ServiceCompletionSerializer(serializers.Serializer):
    """
    Serializer for completing a service.

    This endpoint:
    - Consumes reserved stock
    - Creates SalesTransactions and Expenses
    - Generates unified receipt
    - Updates service status to COMPLETED
    """

    create_receipt = serializers.BooleanField(
        default=True,
        help_text="Create a unified customer receipt"
    )

    def validate(self, data):
        """Validate service can be completed."""
        from utils.enums import ServiceStatus

        service = self.context.get("service")
        if not service:
            raise ValidationError("Service instance required in context.")

        if service.status == ServiceStatus.COMPLETED:
            raise ValidationError("Service is already completed.")

        if service.status == ServiceStatus.CANCELLED:
            raise ValidationError("Cannot complete a cancelled service.")

        return data

    def save(self):
        """Execute service completion workflow."""
        from services.business_logic import ServiceCompletionHandler

        service = self.context.get("service")
        user = self.context.get("request").user if self.context.get("request") else None
        create_receipt = self.validated_data.get("create_receipt", True)

        result = ServiceCompletionHandler.complete_service(
            service=service,
            user=user,
            create_receipt=create_receipt
        )

        return result


class ServiceCancellationSerializer(serializers.Serializer):
    """
    Serializer for cancelling a service.

    Releases all reserved stock and updates service status to CANCELLED.
    """

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Reason for cancellation"
    )

    def validate(self, data):
        """Validate service can be cancelled."""
        from utils.enums import ServiceStatus

        service = self.context.get("service")
        if not service:
            raise ValidationError("Service instance required in context.")

        if service.status == ServiceStatus.COMPLETED:
            raise ValidationError("Cannot cancel a completed service.")

        if service.status == ServiceStatus.CANCELLED:
            raise ValidationError("Service is already cancelled.")

        return data

    def save(self):
        """Execute service cancellation workflow."""
        from services.business_logic import ServiceCancellationHandler

        service = self.context.get("service")
        user = self.context.get("request").user if self.context.get("request") else None
        reason = self.validated_data.get("reason", "")

        result = ServiceCancellationHandler.cancel_service(
            service=service,
            reason=reason,
            user=user
        )

        return result
