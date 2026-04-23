"""
Service API serializers with two-stall architecture support.

Features:
- Stock reservation on service creation
- Stock consumption on service completion
- Revenue attribution (Main vs Sub stall)
- Promo support (free installation, copper tube promos)
"""

from datetime import time
from decimal import Decimal, ROUND_HALF_UP

from clients.models import Client
from django.db import transaction
from installations.models import AirconUnit
from inventory.models import Stall, Stock, StockRequest
from receivables.models import ChequeCollection
from rest_framework import serializers
from sales.models import DocumentType
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
    ApplianceType,
    CompanyAsset,
    JobOrderTemplatePrint,
    PaymentType,
    Service,
    ServiceAppliance,
    ServiceExtraCharge,
    ServiceItemUsed,
    ServicePartTemplate,
    ServicePartTemplateLine,
    ServicePayment,
    ServiceReceipt,
    ServiceRefund,
    TechnicianAssignment,
)
from users.models import CustomUser


class ApplianceTypeSerializer(serializers.ModelSerializer):
    """Serializer for ApplianceType model."""

    class Meta:
        model = ApplianceType
        fields = ["id", "name", "default_labor_warranty_months", "default_unit_warranty_months"]
        read_only_fields = ["id"]


class ServiceReceiptSerializer(serializers.ModelSerializer):
    """CRUD serializer for per-service receipts (supports multiple receipts per service)."""

    class Meta:
        model = ServiceReceipt
        fields = [
            "id",
            "service",
            "receipt_number",
            "receipt_book",
            "document_type",
            "with_2307",
            "amount",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        doc_type = attrs.get(
            "document_type",
            getattr(self.instance, "document_type", DocumentType.OFFICIAL_RECEIPT),
        )
        if doc_type == DocumentType.SALES_INVOICE:
            attrs["with_2307"] = False
        return attrs


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

    item_name = serializers.SerializerMethodField()
    item_sku = serializers.SerializerMethodField()
    item_price = serializers.SerializerMethodField()

    # Promo fields
    apply_copper_tube_promo = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
        help_text="Apply free 10ft copper tube promo"
    )

    # Read-only fields
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False
    )
    free_quantity = serializers.IntegerField(read_only=True)
    promo_name = serializers.CharField(read_only=True)
    charged_quantity = serializers.SerializerMethodField()
    discounted_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = ApplianceItemUsed
        fields = [
            "id",
            "appliance",
            "item",
            "custom_price",
            "custom_description",
            "item_name",
            "item_sku",
            "item_price",
            "quantity",
            "stall_stock_id",
            "is_free",
            "free_quantity",
            "promo_name",
            "charged_quantity",
            "discount_amount",
            "discount_percentage",
            "discount_reason",
            "discounted_price",
            "line_total",
            "apply_copper_tube_promo",
            "is_cancelled",
            "cancelled_at",
            "stock_request_status",
        ]
        read_only_fields = [
            "free_quantity",
            "promo_name",
            "discounted_price",
            "is_cancelled",
            "cancelled_at",
            "stock_request_status",
        ]

    def get_item_name(self, obj):
        if obj.item:
            return obj.item.name
        return obj.custom_description or "Custom Item"

    def get_item_sku(self, obj):
        if obj.item:
            return obj.item.sku
        return None

    def get_item_price(self, obj):
        if obj.item:
            return obj.item.retail_price
        return obj.custom_price

    def get_charged_quantity(self, obj):
        return obj.quantity - obj.free_quantity

    def get_line_total(self, obj):
        return str(obj.line_total)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if getattr(self, '_stock_auto_added', False):
            data['stock_auto_added'] = True
            data['stock_auto_added_qty'] = float(getattr(self, '_stock_deficit', 0))
        return data

    def validate(self, data):
        """Validate stock availability for reservation."""
        item = data.get("item")

        # Custom item — no stock validation needed
        if not item and data.get("custom_price"):
            self._validated_stock = None
            self._insufficient_stock = False
            self._is_custom_item = True
            return data

        self._is_custom_item = False

        if not item and self.instance:
            item = self.instance.item
            data["item"] = item

        if not item:
            raise ValidationError("Either select an inventory item or provide a custom price.")

        qty = data.get("quantity", 1)

        # Resolve stock
        stock = data.get("stall_stock")
        if stock is None:
            if self.instance and self.instance.stall_stock:
                stock = self.instance.stall_stock
            else:
                sub_stall = get_sub_stall()
                if not sub_stall:
                    raise ValidationError("Sub stall not configured in system.")

                stock = Stock.objects.filter(
                    item=item,
                    stall=sub_stall,
                    is_deleted=False
                ).first()

                if stock is None:
                    # No stock record at all — entire quantity is deficit
                    self._validated_stock = None
                    self._insufficient_stock = True
                    self._stock_deficit = Decimal(str(qty))
                    self._resolved_stall = sub_stall
                    return data

            data["stall_stock"] = stock

        if stock.item != item:
            raise ValidationError("Selected stock does not match the item.")

        # Untracked stock — skip all stock validation
        if not stock.track_stock:
            self._validated_stock = stock
            self._insufficient_stock = False
            self._stock_deficit = Decimal('0')
            self._untracked = True
            return data

        self._untracked = False

        # Reset insufficient stock flag
        self._insufficient_stock = False
        self._stock_deficit = Decimal('0')

        if self.instance:
            old_qty = self.instance.quantity
            new_qty = qty
            additional_qty_needed = Decimal(str(new_qty)) - Decimal(str(old_qty))

            if additional_qty_needed > 0:
                available = stock.quantity - stock.reserved_quantity
                if available < additional_qty_needed:
                    self._insufficient_stock = True
                    self._stock_deficit = max(additional_qty_needed - available, Decimal('0'))
        else:
            available = stock.quantity - stock.reserved_quantity
            qty_dec = Decimal(str(qty))
            if available < qty_dec:
                self._insufficient_stock = True
                self._stock_deficit = max(qty_dec - available, Decimal('0'))

        self._validated_stock = stock
        return data

    def create(self, validated_data):
        """
        Create item usage record and RESERVE stock (don't consume yet).
        If stock is insufficient, creates a StockRequest for admin approval.
        Custom items skip stock entirely.
        Untracked items skip stock reservation.
        """
        apply_copper_promo = validated_data.pop("apply_copper_tube_promo", False)

        # Custom item — no stock interaction
        if getattr(self, '_is_custom_item', False):
            return super().create(validated_data)

        # Untracked stock — record link but skip reservation
        if getattr(self, '_untracked', False):
            validated_data["stall_stock"] = self._validated_stock
            return super().create(validated_data)

        stock = self._validated_stock
        qty = validated_data.get("quantity", 1)
        is_free = validated_data.get("is_free", False)

        with transaction.atomic():
            if getattr(self, '_insufficient_stock', False):
                from django.contrib.auth import get_user_model
                from notifications.models import Notification, NotificationType
                request_user = self.context.get('request')
                requester = request_user.user if request_user else None
                is_admin = getattr(requester, 'role', None) == 'admin'
                stall = stock.stall if stock else getattr(self, '_resolved_stall', None)

                if is_admin:
                    # Admin: auto-add the deficit directly to stock and reserve
                    stock.quantity += self._stock_deficit
                    stock.save(update_fields=['quantity', 'updated_at'])
                    reserved_stock = StockReservationManager.reserve_stock(
                        item=validated_data["item"],
                        quantity=qty,
                        stall_stock=stock
                    )
                    validated_data["stall_stock"] = reserved_stock
                    aiu = super().create(validated_data)
                    self._stock_auto_added = True

                    # Notify all admins that stock was auto-added
                    User = get_user_model()
                    admins = User.objects.filter(role='admin', is_active=True)
                    full_name = requester.get_full_name() if requester else 'Admin'
                    Notification.objects.bulk_create([
                        Notification(
                            user=admin_user,
                            type=NotificationType.STOCK_ADDED_BY_ADMIN,
                            title="Stock Auto-Added",
                            message=(
                                f"{full_name} added {self._stock_deficit} "
                                f"{validated_data['item'].unit_of_measure} of "
                                f"'{validated_data['item'].name}' to stock for "
                                f"service #{aiu.appliance.service_id}."
                            ),
                            data={
                                "item_name": validated_data["item"].name,
                                "quantity": float(self._stock_deficit),
                                "service_id": aiu.appliance.service_id,
                                "added_by": full_name,
                            },
                        )
                        for admin_user in admins
                    ])
                else:
                    # Non-admin: create stock request awaiting admin approval
                    if stock:
                        validated_data["stall_stock"] = stock
                    validated_data["stock_request_status"] = "pending"
                    aiu = super().create(validated_data)

                    StockRequest.objects.create(
                        item=validated_data["item"],
                        stall=stall,
                        requested_quantity=self._stock_deficit,
                        source="service_appliance",
                        service=aiu.appliance.service,
                        appliance_item=aiu,
                        notes=f"Auto-created: insufficient stock when adding to service #{aiu.appliance.service_id}",
                        requested_by=requester,
                    )

                    User = get_user_model()
                    admins = User.objects.filter(role='admin', is_active=True)
                    clerk_name = requester.get_full_name() if requester else 'A clerk'
                    Notification.objects.bulk_create([
                        Notification(
                            user=admin_user,
                            type=NotificationType.STOCK_REQUEST_CREATED,
                            title="Stock Request: Approval Needed",
                            message=(
                                f"{clerk_name} needs {self._stock_deficit} "
                                f"{validated_data['item'].unit_of_measure} of "
                                f"'{validated_data['item'].name}' for service "
                                f"#{aiu.appliance.service_id}."
                            ),
                            data={
                                "item_name": validated_data["item"].name,
                                "quantity": float(self._stock_deficit),
                                "service_id": aiu.appliance.service_id,
                            },
                        )
                        for admin_user in admins
                    ])
            else:
                # Sufficient stock — normal reservation flow
                reserved_stock = StockReservationManager.reserve_stock(
                    item=validated_data["item"],
                    quantity=qty,
                    stall_stock=stock
                )
                validated_data["stall_stock"] = reserved_stock
                aiu = super().create(validated_data)

            if apply_copper_promo and not is_free:
                free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(aiu)
                if applied:
                    aiu.save(update_fields=["free_quantity", "promo_name"])

        return aiu

    def update(self, instance, validated_data):
        """
        Update item usage and adjust reservation.
        Handles:
          - custom→custom: no stock interaction
          - inventory→custom: release old stock
          - custom→inventory: reserve new stock
          - inventory→inventory: adjust reservation by qty diff
        """
        apply_copper_promo = validated_data.pop("apply_copper_tube_promo", False)
        was_custom = instance.is_custom_item
        is_now_custom = getattr(self, '_is_custom_item', False)

        with transaction.atomic():
            if was_custom and is_now_custom:
                # custom → custom: no stock interaction
                return super().update(instance, validated_data)

            if not was_custom and is_now_custom:
                # inventory → custom: release old reservation
                if instance.stall_stock and instance.item:
                    StockReservationManager.release_reservation(
                        item=instance.item,
                        quantity=instance.quantity,
                        stall_stock=instance.stall_stock
                    )
                validated_data['stall_stock'] = None
                validated_data['stock_request_status'] = None
                return super().update(instance, validated_data)

            if was_custom and not is_now_custom:
                # custom → inventory: reserve new stock
                stock = self._validated_stock
                new_qty = validated_data.get("quantity", 1)
                StockReservationManager.reserve_stock(
                    item=validated_data["item"],
                    quantity=new_qty,
                    stall_stock=stock
                )
                validated_data['stall_stock'] = stock
                validated_data['custom_price'] = None
                instance = super().update(instance, validated_data)
                if apply_copper_promo and not instance.is_free:
                    free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(instance)
                    if applied:
                        instance.save(update_fields=["free_quantity", "promo_name"])
                return instance

            # inventory → inventory: adjust reservation by qty diff
            stock = self._validated_stock
            old_qty = instance.quantity
            new_qty = validated_data.get("quantity", old_qty)
            diff = new_qty - old_qty

            if diff > 0:
                StockReservationManager.reserve_stock(
                    item=instance.item,
                    quantity=diff,
                    stall_stock=stock
                )
            elif diff < 0:
                StockReservationManager.release_reservation(
                    item=instance.item,
                    quantity=abs(diff),
                    stall_stock=stock
                )

            instance = super().update(instance, validated_data)

            if apply_copper_promo and not instance.is_free:
                free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(instance)
                if applied:
                    instance.save(update_fields=["free_quantity", "promo_name"])

        return instance


class ServiceItemUsedSerializer(serializers.ModelSerializer):
    """
    Serializer for parts used at the service level (not tied to any appliance).

    Used for pre-installation work like chipping where the AC unit hasn't been
    added yet. Same reservation flow as ApplianceItemUsedSerializer.
    """

    stall_stock_id = serializers.PrimaryKeyRelatedField(
        queryset=Stock.objects.all(),
        source="stall_stock",
        write_only=True,
        required=False,
        help_text="Optional: if omitted, system auto-resolves Sub stall stock for the item.",
    )

    item_name = serializers.SerializerMethodField()
    item_sku = serializers.SerializerMethodField()
    item_price = serializers.SerializerMethodField()

    apply_copper_tube_promo = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
        help_text="Apply free 10ft copper tube promo"
    )

    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False
    )
    free_quantity = serializers.IntegerField(read_only=True)
    promo_name = serializers.CharField(read_only=True)
    charged_quantity = serializers.SerializerMethodField()
    discounted_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = ServiceItemUsed
        fields = [
            "id",
            "service",
            "item",
            "custom_price",
            "custom_description",
            "item_name",
            "item_sku",
            "item_price",
            "quantity",
            "stall_stock_id",
            "is_free",
            "free_quantity",
            "promo_name",
            "charged_quantity",
            "discount_amount",
            "discount_percentage",
            "discount_reason",
            "discounted_price",
            "line_total",
            "apply_copper_tube_promo",
            "is_cancelled",
            "cancelled_at",
            "stock_request_status",
        ]
        read_only_fields = [
            "free_quantity",
            "promo_name",
            "discounted_price",
            "is_cancelled",
            "cancelled_at",
            "stock_request_status",
        ]

    def get_item_name(self, obj):
        if obj.item:
            return obj.item.name
        return obj.custom_description or "Custom Item"

    def get_item_sku(self, obj):
        if obj.item:
            return obj.item.sku
        return None

    def get_item_price(self, obj):
        if obj.item:
            return obj.item.retail_price
        return obj.custom_price

    def get_charged_quantity(self, obj):
        return obj.quantity - obj.free_quantity

    def get_line_total(self, obj):
        return str(obj.line_total)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if getattr(self, '_stock_auto_added', False):
            data['stock_auto_added'] = True
            data['stock_auto_added_qty'] = float(getattr(self, '_stock_deficit', 0))
        return data

    def validate(self, data):
        item = data.get("item")

        # Custom item — no stock validation needed
        if not item and data.get("custom_price"):
            self._validated_stock = None
            self._insufficient_stock = False
            self._is_custom_item = True
            return data

        self._is_custom_item = False

        if not item and self.instance:
            item = self.instance.item
            data["item"] = item

        if not item:
            raise ValidationError("Either select an inventory item or provide a custom price.")

        qty = data.get("quantity", 1)

        stock = data.get("stall_stock")
        if stock is None:
            if self.instance and self.instance.stall_stock:
                stock = self.instance.stall_stock
            else:
                sub_stall = get_sub_stall()
                if not sub_stall:
                    raise ValidationError("Sub stall not configured in system.")

                stock = Stock.objects.filter(
                    item=item,
                    stall=sub_stall,
                    is_deleted=False
                ).first()

                if stock is None:
                    self._validated_stock = None
                    self._insufficient_stock = True
                    self._stock_deficit = Decimal(str(qty))
                    self._resolved_stall = sub_stall
                    return data

            data["stall_stock"] = stock

        if stock.item != item:
            raise ValidationError("Selected stock does not match the item.")

        # Untracked stock — skip all stock validation
        if not stock.track_stock:
            self._validated_stock = stock
            self._insufficient_stock = False
            self._stock_deficit = Decimal('0')
            self._untracked = True
            return data

        self._untracked = False

        self._insufficient_stock = False
        self._stock_deficit = Decimal('0')

        if self.instance:
            old_qty = self.instance.quantity
            new_qty = qty
            additional_qty_needed = Decimal(str(new_qty)) - Decimal(str(old_qty))

            if additional_qty_needed > 0:
                available = stock.quantity - stock.reserved_quantity
                if available < additional_qty_needed:
                    self._insufficient_stock = True
                    self._stock_deficit = max(additional_qty_needed - available, Decimal('0'))
        else:
            available = stock.quantity - stock.reserved_quantity
            qty_dec = Decimal(str(qty))
            if available < qty_dec:
                self._insufficient_stock = True
                self._stock_deficit = max(qty_dec - available, Decimal('0'))

        self._validated_stock = stock
        return data

    def create(self, validated_data):
        apply_copper_promo = validated_data.pop("apply_copper_tube_promo", False)

        # Custom item — no stock interaction
        if getattr(self, '_is_custom_item', False):
            return super().create(validated_data)

        # Untracked stock — record link but skip reservation
        if getattr(self, '_untracked', False):
            validated_data["stall_stock"] = self._validated_stock
            return super().create(validated_data)

        stock = self._validated_stock
        qty = validated_data.get("quantity", 1)

        with transaction.atomic():
            if getattr(self, '_insufficient_stock', False):
                from django.contrib.auth import get_user_model
                from notifications.models import Notification, NotificationType
                request_user = self.context.get('request')
                requester = request_user.user if request_user else None
                is_admin = getattr(requester, 'role', None) == 'admin'
                stall = stock.stall if stock else getattr(self, '_resolved_stall', None)

                if is_admin:
                    # Admin: auto-add the deficit directly to stock and reserve
                    stock.quantity += self._stock_deficit
                    stock.save(update_fields=['quantity', 'updated_at'])
                    reserved_stock = StockReservationManager.reserve_stock(
                        item=validated_data["item"],
                        quantity=qty,
                        stall_stock=stock
                    )
                    validated_data["stall_stock"] = reserved_stock
                    siu = super().create(validated_data)
                    self._stock_auto_added = True

                    # Notify all admins that stock was auto-added
                    User = get_user_model()
                    admins = User.objects.filter(role='admin', is_active=True)
                    full_name = requester.get_full_name() if requester else 'Admin'
                    Notification.objects.bulk_create([
                        Notification(
                            user=admin_user,
                            type=NotificationType.STOCK_ADDED_BY_ADMIN,
                            title="Stock Auto-Added",
                            message=(
                                f"{full_name} added {self._stock_deficit} "
                                f"{validated_data['item'].unit_of_measure} of "
                                f"'{validated_data['item'].name}' to stock for "
                                f"service #{siu.service_id}."
                            ),
                            data={
                                "item_name": validated_data["item"].name,
                                "quantity": float(self._stock_deficit),
                                "service_id": siu.service_id,
                                "added_by": full_name,
                            },
                        )
                        for admin_user in admins
                    ])
                else:
                    # Non-admin: create stock request awaiting admin approval
                    if stock:
                        validated_data["stall_stock"] = stock
                    validated_data["stock_request_status"] = "pending"
                    siu = super().create(validated_data)

                    StockRequest.objects.create(
                        item=validated_data["item"],
                        stall=stall,
                        requested_quantity=self._stock_deficit,
                        source="service",
                        service=siu.service,
                        service_item=siu,
                        notes=f"Auto-created: insufficient stock when adding to service #{siu.service_id}",
                        requested_by=requester,
                    )

                    User = get_user_model()
                    admins = User.objects.filter(role='admin', is_active=True)
                    clerk_name = requester.get_full_name() if requester else 'A clerk'
                    Notification.objects.bulk_create([
                        Notification(
                            user=admin_user,
                            type=NotificationType.STOCK_REQUEST_CREATED,
                            title="Stock Request: Approval Needed",
                            message=(
                                f"{clerk_name} needs {self._stock_deficit} "
                                f"{validated_data['item'].unit_of_measure} of "
                                f"'{validated_data['item'].name}' for service "
                                f"#{siu.service_id}."
                            ),
                            data={
                                "item_name": validated_data["item"].name,
                                "quantity": float(self._stock_deficit),
                                "service_id": siu.service_id,
                            },
                        )
                        for admin_user in admins
                    ])
            else:
                reserved_stock = StockReservationManager.reserve_stock(
                    item=validated_data["item"],
                    quantity=qty,
                    stall_stock=stock
                )
                validated_data["stall_stock"] = reserved_stock
                siu = super().create(validated_data)

            if apply_copper_promo and not validated_data.get("is_free", False):
                free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(siu)
                if applied:
                    siu.save(update_fields=["free_quantity", "promo_name"])

        return siu

    def update(self, instance, validated_data):
        apply_copper_promo = validated_data.pop("apply_copper_tube_promo", False)
        was_custom = instance.is_custom_item
        is_now_custom = getattr(self, '_is_custom_item', False)

        with transaction.atomic():
            if was_custom and is_now_custom:
                return super().update(instance, validated_data)

            if not was_custom and is_now_custom:
                # inventory → custom: release old reservation
                if instance.stall_stock and instance.item:
                    StockReservationManager.release_reservation(
                        item=instance.item,
                        quantity=instance.quantity,
                        stall_stock=instance.stall_stock
                    )
                validated_data['stall_stock'] = None
                validated_data['stock_request_status'] = None
                return super().update(instance, validated_data)

            if was_custom and not is_now_custom:
                # custom → inventory: reserve new stock
                stock = self._validated_stock
                new_qty = validated_data.get("quantity", 1)
                StockReservationManager.reserve_stock(
                    item=validated_data["item"],
                    quantity=new_qty,
                    stall_stock=stock
                )
                validated_data['stall_stock'] = stock
                validated_data['custom_price'] = None
                instance = super().update(instance, validated_data)
                if apply_copper_promo and not instance.is_free:
                    free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(instance)
                    if applied:
                        instance.save(update_fields=["free_quantity", "promo_name"])
                return instance

            # inventory → inventory: adjust reservation by qty diff
            stock = self._validated_stock
            old_qty = instance.quantity
            new_qty = validated_data.get("quantity", old_qty)
            diff = new_qty - old_qty

            if diff > 0:
                StockReservationManager.reserve_stock(
                    item=instance.item,
                    quantity=diff,
                    stall_stock=stock
                )
            elif diff < 0:
                StockReservationManager.release_reservation(
                    item=instance.item,
                    quantity=abs(diff),
                    stall_stock=stock
                )

            instance = super().update(instance, validated_data)

            if apply_copper_promo and not instance.is_free:
                free_qty, charged_qty, applied = PromoManager.apply_copper_tube_free_10ft(instance)
                if applied:
                    instance.save(update_fields=["free_quantity", "promo_name"])

        return instance


class TechnicianAssignmentPayloadSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating technician assignments (write operations)."""

    technician = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.all_objects.all(),
        required=True
    )
    appliance = serializers.PrimaryKeyRelatedField(
        queryset=ServiceAppliance.objects.all(),
        required=False,
        allow_null=True
    )

    def validate_technician(self, technician):
        # Ensure the user has an appropriate role regardless of create/update.
        if not technician.is_technician and technician.role not in ('admin', 'manager'):
            raise serializers.ValidationError(
                f"{technician.get_full_name()} is not designated as a technician."
            )
        # On create (root has no instance): only active technicians may be newly assigned.
        # On update: allow inactive so existing assignments with deactivated staff can be preserved.
        root = self.root
        is_update = (root is not self) and (root.instance is not None)
        if not is_update and (not technician.is_active or technician.is_deleted):
            raise serializers.ValidationError(
                f"{technician.get_full_name()} is inactive and cannot be assigned."
            )
        return technician

    class Meta:
        model = TechnicianAssignment
        fields = [
            "id",
            "service",
            "appliance",
            "technician",
            "assignment_type",
            "note",
        ]
        extra_kwargs = {
            "service": {"required": False},  # Set by parent serializer during nested creation
            "id": {"read_only": True},
        }


class TechnicianAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for reading technician assignments."""

    technician = serializers.PrimaryKeyRelatedField(read_only=True)
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

    # Nested appliance type (read for GET, write accepts ID)
    appliance_type = ApplianceTypeSerializer(read_only=True)
    appliance_type_id = serializers.PrimaryKeyRelatedField(
        queryset=ApplianceType.objects.all(),
        source='appliance_type',
        write_only=True,
        allow_null=True,
        required=False
    )

    # Aircon installation data (optional)
    aircon_installation_data = serializers.DictField(
        write_only=True,
        required=False,
        allow_null=True,
        help_text="Aircon installation details for creating installation records"
    )

    # Aircon model name (read-only, for pre-order display)
    aircon_model_name = serializers.SerializerMethodField()

    # Read-only computed fields
    assigned_technician_name = serializers.CharField(
        source="assigned_technician.get_full_name",
        read_only=True,
        allow_null=True
    )
    items_checked_by_name = serializers.CharField(
        source="items_checked_by.get_full_name",
        read_only=True,
        allow_null=True
    )
    discounted_labor_fee = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    is_labor_warranty_active = serializers.BooleanField(read_only=True)
    is_unit_warranty_active = serializers.BooleanField(read_only=True)
    total_parts_cost = serializers.SerializerMethodField()

    class Meta:
        model = ServiceAppliance
        fields = [
            "id",
            "service",
            "appliance_type",
            "appliance_type_id",
            "brand",
            "model",
            "serial_number",
            "issue_reported",
            "diagnosis_notes",
            "status",
            "assigned_technician",
            "assigned_technician_name",
            "labor_fee",
            "labor_is_free",
            "labor_original_amount",
            "unit_price",
            "labor_discount_amount",
            "labor_discount_percentage",
            "labor_discount_reason",
            "labor_warranty_months",
            "unit_warranty_months",
            "warranty_notes",
            "warranty_start_date",
            "labor_warranty_end_date",
            "unit_warranty_end_date",
            "is_labor_warranty_active",
            "is_unit_warranty_active",
            "discounted_labor_fee",
            "aircon_installation_data",
            "unit_type",
            "aircon_model",
            "aircon_model_name",
            "items_used",
            "technician_assignments",
            "total_parts_cost",
            "total_service_fee",
            "auto_adjust_labor",
            "parts_needed_notes",
            "items_checked",
            "items_checked_by",
            "items_checked_by_name",
            "items_checked_at",
        ]
        read_only_fields = [
            "labor_original_amount",
            "discounted_labor_fee",
            "warranty_start_date",
            "labor_warranty_end_date",
            "unit_warranty_end_date",
            "is_labor_warranty_active",
            "is_unit_warranty_active",
            "items_checked",
            "items_checked_by",
            "items_checked_at",
        ]

    def get_aircon_model_name(self, obj):
        """Return the aircon model display name for pre-order units."""
        if obj.aircon_model:
            brand_name = obj.aircon_model.brand.name if obj.aircon_model.brand else ''
            return f"{brand_name} {obj.aircon_model.name}".strip()
        return None

    def get_total_parts_cost(self, obj):
        """Calculate total cost of parts including discounts (excluding free items/quantities)."""
        total = Decimal('0.00')
        for item_used in obj.items_used.all():
            # Use the line_total property which already accounts for discounts
            total += item_used.line_total
        # Round to 2 decimal places to prevent validation errors
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def create(self, validated_data):
        """Create appliance with items."""
        items_data = validated_data.pop("items_used", [])
        aircon_install_data = validated_data.pop("aircon_installation_data", None)

        with transaction.atomic():
            appliance = ServiceAppliance.objects.create(**validated_data)

            # Create aircon installation if data provided
            if aircon_install_data:
                self._create_aircon_installation(appliance, aircon_install_data)

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
        """Update appliance and items, handling unit type changes."""
        items_data = validated_data.pop("items_used", None)
        aircon_install_data = validated_data.pop("aircon_installation_data", None)

        with transaction.atomic():
            # Handle aircon installation data changes (unit type switch, new unit, etc.)
            if aircon_install_data is not None:
                self._handle_aircon_update(instance, aircon_install_data)

            # Update appliance fields
            instance = super().update(instance, validated_data)

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

    def _handle_aircon_update(self, appliance, install_data):
        """
        Handle aircon installation changes on update.
        Releases old brand_new unit if switching to second_hand or a different unit.
        Links new brand_new unit if specified.
        """
        from installations.models import AirconUnit
        from django.utils import timezone

        service = appliance.service
        new_unit_type = install_data.get('unit_type')
        new_unit_id = install_data.get('unit_id')

        # Find old linked unit (if any) by matching serial number
        old_unit = None
        if appliance.serial_number:
            old_unit = AirconUnit.objects.filter(
                installation_service=service,
                serial_number=appliance.serial_number,
            ).first()

        # Release old unit if switching away from it
        if old_unit and (
            new_unit_type in ('second_hand', 'pre_order')
            or (new_unit_type == 'brand_new' and new_unit_id and new_unit_id != old_unit.id)
        ):
            old_unit.installation_service = None
            old_unit.reserved_by = None
            old_unit.reserved_at = None
            old_unit.save(update_fields=[
                'installation_service', 'reserved_by', 'reserved_at', 'updated_at'
            ])

        if new_unit_type == 'brand_new':
            unit_id = new_unit_id
            if not unit_id:
                raise serializers.ValidationError({
                    'aircon_installation_data': 'unit_id is required for brand_new units'
                })

            try:
                unit = AirconUnit.objects.get(id=unit_id)
            except AirconUnit.DoesNotExist:
                raise serializers.ValidationError({
                    'aircon_installation_data': f'Aircon unit {unit_id} not found'
                })

            # Skip if same unit already linked
            if old_unit and old_unit.id == unit.id:
                return

            # Link new unit to service
            unit.installation_service = service
            unit.reserved_by = service.client
            unit.reserved_at = timezone.now()
            unit.save(update_fields=[
                'installation_service', 'reserved_by', 'reserved_at', 'updated_at'
            ])

            # Update appliance with unit details
            appliance.brand = unit.model.brand.name if unit.model and unit.model.brand else ''
            appliance.model = unit.model.name if unit.model else ''
            appliance.serial_number = unit.serial_number
            appliance.unit_type = 'brand_new'
            appliance.aircon_model = None
            # Support unit_price override for brand_new units
            unit_price = install_data.get('unit_price')
            if unit_price is not None:
                appliance.unit_price = Decimal(str(unit_price))
            else:
                appliance.unit_price = None  # brand_new uses model selling price
            appliance.save(update_fields=['brand', 'model', 'serial_number', 'unit_price', 'unit_type', 'aircon_model'])

            # Recalculate revenue
            RevenueCalculator.calculate_service_revenue(service, save=True)

        elif new_unit_type == 'second_hand':
            # Clear unit_price if not provided, or set it
            unit_price = install_data.get('unit_price')
            if unit_price is not None:
                appliance.unit_price = Decimal(str(unit_price))
            else:
                appliance.unit_price = None
            appliance.unit_type = 'second_hand'
            appliance.aircon_model = None
            appliance.save(update_fields=['unit_price', 'unit_type', 'aircon_model'])

            # Recalculate revenue
            RevenueCalculator.calculate_service_revenue(service, save=True)

        elif new_unit_type == 'pre_order':
            # Pre-order: select a model (not a specific unit)
            from installations.models import AirconModel

            model_id = install_data.get('model_id')
            if not model_id:
                raise serializers.ValidationError({
                    'aircon_installation_data': 'model_id is required for pre_order units'
                })

            try:
                aircon_model = AirconModel.objects.select_related('brand').get(id=model_id)
            except AirconModel.DoesNotExist:
                raise serializers.ValidationError({
                    'aircon_installation_data': f'Aircon model {model_id} not found'
                })

            appliance.brand = aircon_model.brand.name if aircon_model.brand else ''
            appliance.model = aircon_model.name
            appliance.serial_number = ''
            appliance.unit_type = 'pre_order'
            appliance.aircon_model = aircon_model

            unit_price = install_data.get('unit_price')
            if unit_price is not None:
                appliance.unit_price = Decimal(str(unit_price))
            else:
                appliance.unit_price = aircon_model.selling_price

            appliance.save(update_fields=[
                'brand', 'model', 'serial_number', 'unit_price',
                'unit_type', 'aircon_model',
            ])

            # Recalculate revenue
            RevenueCalculator.calculate_service_revenue(service, save=True)

    def _create_aircon_installation(self, appliance, install_data):
        """
        Link aircon unit to installation service.
        Units are linked directly to the service without intermediate AirconInstallation model.
        """
        from installations.models import AirconUnit
        from django.utils import timezone

        unit_type = install_data.get('unit_type')
        service = appliance.service

        if unit_type == 'brand_new':
            # Get unit from inventory
            unit_id = install_data.get('unit_id')
            if not unit_id:
                raise serializers.ValidationError({
                    'aircon_installation_data': 'unit_id is required for brand_new units'
                })

            try:
                unit = AirconUnit.objects.get(id=unit_id)
            except AirconUnit.DoesNotExist:
                raise serializers.ValidationError({
                    'aircon_installation_data': f'Aircon unit {unit_id} not found'
                })

            # Update service notes with unit information
            unit_info = f"Brand New Unit: {unit.serial_number}, Model: {unit.model}"
            if service.notes:
                service.notes = f"{service.notes}\n{unit_info}"
            else:
                service.notes = unit_info
            service.save(update_fields=['notes', 'updated_at'])

            # Link unit to installation service and reserve it for the client
            unit.installation_service = service
            unit.reserved_by = service.client
            unit.reserved_at = timezone.now()
            unit.save(update_fields=['installation_service', 'reserved_by', 'reserved_at', 'updated_at'])

            # Update appliance with unit details
            appliance.brand = unit.model.brand.name if unit.model and unit.model.brand else ''
            appliance.model = unit.model.name if unit.model else ''
            appliance.serial_number = unit.serial_number
            appliance.unit_type = 'brand_new'
            appliance.aircon_model = None
            # Support unit_price override for brand_new units
            unit_price = install_data.get('unit_price')
            if unit_price is not None:
                appliance.unit_price = Decimal(str(unit_price))
            else:
                appliance.unit_price = None  # brand_new uses model selling price
            appliance.save(update_fields=['brand', 'model', 'serial_number', 'unit_price', 'unit_type', 'aircon_model'])

            # Recalculate service revenue to include unit price
            RevenueCalculator.calculate_service_revenue(service, save=True)

        elif unit_type == 'second_hand':
            # Use manual entry data from appliance
            if not appliance.brand:
                raise serializers.ValidationError({
                    'aircon_installation_data': 'brand is required for second_hand units'
                })

            # Save custom unit price if provided
            unit_price = install_data.get('unit_price')
            if unit_price is not None:
                appliance.unit_price = Decimal(str(unit_price))
                appliance.save(update_fields=['unit_price'])

            # Store unit_type
            appliance.unit_type = 'second_hand'
            appliance.aircon_model = None
            appliance.save(update_fields=['unit_price', 'unit_type', 'aircon_model'])

            # Add notes to service about second-hand unit
            unit_info = f"Second-Hand Unit: {appliance.brand}"
            if service.notes:
                service.notes = f"{service.notes}\n{unit_info}"
            else:
                service.notes = unit_info
            service.save(update_fields=['notes', 'updated_at'])

            # Recalculate service revenue to include unit price
            RevenueCalculator.calculate_service_revenue(service, save=True)

        elif unit_type == 'pre_order':
            # Pre-order: select a model (not a specific unit) for pricing
            from installations.models import AirconModel

            model_id = install_data.get('model_id')
            if not model_id:
                raise serializers.ValidationError({
                    'aircon_installation_data': 'model_id is required for pre_order units'
                })

            try:
                aircon_model = AirconModel.objects.select_related('brand').get(id=model_id)
            except AirconModel.DoesNotExist:
                raise serializers.ValidationError({
                    'aircon_installation_data': f'Aircon model {model_id} not found'
                })

            # Set appliance details from the model
            appliance.brand = aircon_model.brand.name if aircon_model.brand else ''
            appliance.model = aircon_model.name
            appliance.serial_number = ''  # No serial number yet
            appliance.unit_type = 'pre_order'
            appliance.aircon_model = aircon_model

            # Set unit_price from override or model's selling price
            unit_price = install_data.get('unit_price')
            if unit_price is not None:
                appliance.unit_price = Decimal(str(unit_price))
            else:
                appliance.unit_price = aircon_model.selling_price

            appliance.save(update_fields=[
                'brand', 'model', 'serial_number', 'unit_price',
                'unit_type', 'aircon_model',
            ])

            # Add notes to service
            unit_info = f"Pre-Order Unit: {aircon_model.brand.name if aircon_model.brand else ''} {aircon_model.name}"
            if service.notes:
                service.notes = f"{service.notes}\n{unit_info}"
            else:
                service.notes = unit_info
            service.save(update_fields=['notes', 'updated_at'])

            # Recalculate service revenue to include unit price
            RevenueCalculator.calculate_service_revenue(service, save=True)


class NestedClientSerializer(serializers.ModelSerializer):
    """Nested client serializer for read operations."""
    class Meta:
        model = Client
        fields = ['id', 'full_name', 'contact_number', 'address']


class NestedStallSerializer(serializers.ModelSerializer):
    """Nested stall serializer for read operations."""
    class Meta:
        model = Stall
        fields = ['id', 'name']


class ServiceExtraChargeSerializer(serializers.ModelSerializer):
    """CRUD serializer for service-level extra charges (e.g. dismantle fee)."""

    created_by_name = serializers.CharField(
        source="created_by.get_full_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = ServiceExtraCharge
        fields = [
            "id",
            "service",
            "description",
            "amount",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_by_name", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class ServiceSerializer(serializers.ModelSerializer):
    """
    Service serializer with two-stall architecture support.

    Handles:
    - Service creation with stock reservation
    - Revenue calculation and attribution
    - Service completion workflow
    - Aircon installation (brand new and second-hand units)
    """

    appliances = ServiceApplianceSerializer(many=True, required=False)
    receipts = ServiceReceiptSerializer(many=True, read_only=True)
    extra_charges = ServiceExtraChargeSerializer(many=True, read_only=True)
    payments = serializers.SerializerMethodField()
    refunds = serializers.SerializerMethodField()
    installation_units = serializers.SerializerMethodField()
    has_pending_items = serializers.BooleanField(read_only=True)
    service_items_checked_by_name = serializers.CharField(
        source="service_items_checked_by.get_full_name",
        read_only=True,
        allow_null=True,
    )
    discount_applied_by_name = serializers.CharField(
        source="discount_applied_by.get_full_name",
        read_only=True,
        allow_null=True,
    )

    # Write-only fields for datetime inputs from frontend
    appointment_datetime = serializers.DateTimeField(write_only=True, required=False, allow_null=True)
    reinstall_appointment_datetime = serializers.DateTimeField(write_only=True, required=False, allow_null=True)
    pickup_date = serializers.DateTimeField(required=False, allow_null=True)
    delivery_date = serializers.DateTimeField(required=False, allow_null=True)
    received_at = serializers.DateTimeField(required=False, allow_null=True)
    create_reinstall = serializers.BooleanField(write_only=True, required=False, default=False)
    reinstall_same_address = serializers.BooleanField(write_only=True, required=False, default=True)
    reinstall_override_address = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    reinstall_override_contact_person = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    reinstall_override_contact_number = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    # Aircon installation fields (write-only)
    aircon_installation_data = serializers.DictField(write_only=True, required=False, allow_null=True,
        help_text="Installation data for aircon units (brand new or second-hand)")

    # Read-only fields
    client_name = serializers.CharField(source="client.full_name", read_only=True)
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
    total_paid = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    balance_due = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    net_revenue = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    has_refunds = serializers.BooleanField(read_only=True)
    payment_status = serializers.SerializerMethodField()
    next_schedule = serializers.SerializerMethodField()

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
            "service_leg",
            "linked_parent_service",
            "related_transaction",
            "related_sub_transaction",
            "override_address",
            "override_contact_person",
            "override_contact_number",
            "pickup_date",
            "delivery_date",
            "received_at",
            "appointment_datetime",
            "reinstall_appointment_datetime",
            "create_reinstall",
            "reinstall_same_address",
            "reinstall_override_address",
            "reinstall_override_contact_person",
            "reinstall_override_contact_number",
            "status",
            "created_at",
            "updated_at",
            "main_stall_revenue",
            "sub_stall_revenue",
            "total_revenue",
            "total_paid",
            "balance_due",
            "net_revenue",
            "has_refunds",
            "payment_status",
            # Cancellation fields
            "cancellation_reason",
            "cancellation_date",
            # Refund fields
            "total_refunded",
            "last_refund_date",
            # Discount fields
            "service_discount_amount",
            "service_discount_percentage",
            "discount_reason",
            "discount_applied_by_name",
            "discount_applied_at",
            "aircon_installation_data",
            "installation_units",
            "appliances",
            "technician_assignments",
            "payments",
            "refunds",
            "next_schedule",
            "has_pending_items",
            # Service-level items review
            "service_parts_needed_notes",
            "service_items_checked",
            "service_items_checked_by",
            "service_items_checked_by_name",
            "service_items_checked_at",
            # BIR receipts (multiple receipts per service)
            "receipts",
            # Extra charges (additional fees not tied to inventory items)
            "extra_charges",
            # Backdating
            "transaction_date",
            # Back job / re-service
            "is_back_job",
            "back_job_parent",
            "back_job_reason",
            # Completion & claim tracking
            "completed_at",
            "claimed_at",
            # Forfeiture / unclaimed policy
            "is_forfeited",
            "forfeited_at",
            "forfeiture_type",
            "forfeiture_notes",
            "acquisition_price",
            # Complementary / warranty tracking
            "is_complementary",
            "complementary_reason",
        ]
        read_only_fields = [
            "main_stall_revenue",
            "sub_stall_revenue",
            "total_revenue",
            "total_paid",
            "balance_due",
            "net_revenue",
            "has_refunds",
            "payment_status",
            "created_at",
            "updated_at",
            "cancellation_date",
            "total_refunded",
            "last_refund_date",
            "has_pending_items",
            "service_items_checked",
            "service_items_checked_by",
            "service_items_checked_at",
            "completed_at",
            "forfeited_at",
        ]

    def get_fields(self):
        """Dynamically select technician_assignments serializer based on request method."""
        fields = super().get_fields()

        # Use payload serializer for write operations, regular serializer for reads
        request = self.context.get('request')
        if request and request.method in ['POST', 'PUT', 'PATCH']:
            # Write operations - use IDs
            fields['technician_assignments'] = TechnicianAssignmentPayloadSerializer(
                many=True,
                required=False
            )
        else:
            # Read operations - use nested objects
            fields['client'] = NestedClientSerializer(read_only=True)
            fields['stall'] = NestedStallSerializer(read_only=True)
            fields['technician_assignments'] = TechnicianAssignmentSerializer(
                many=True,
                required=False
            )

        return fields

    def validate(self, attrs):
        doc_type = attrs.get(
            "document_type",
            getattr(self.instance, "document_type", DocumentType.OFFICIAL_RECEIPT),
        )
        if doc_type == DocumentType.SALES_INVOICE:
            attrs["with_2307"] = False
        return attrs

    def get_payment_status(self, obj):
        """Return the DB payment status which accounts for refunds."""
        # Use the stored payment_status which is kept in sync by
        # update_payment_status() (called on payment save and refund).
        status = obj.payment_status
        if status:
            return status
        # Fallback for services with no revenue yet
        total_cost = float(obj.total_revenue or 0)
        if total_cost == 0:
            return "pending"
        return "unpaid"

    def get_payments(self, obj):
        """Get all payments for this service."""
        payments = obj.payments.all()
        return ServicePaymentSerializer(payments, many=True).data

    def get_refunds(self, obj):
        """Get all refunds for this service."""
        refunds = obj.refunds.all()
        return ServiceRefundSerializer(refunds, many=True).data

    def get_installation_units(self, obj):
        """Get all aircon units for installation services."""
        if obj.service_type != 'installation':
            return []

        from installations.api.serializers import AirconUnitSerializer
        units = obj.installation_units.all()
        return AirconUnitSerializer(units, many=True).data

    def get_next_schedule(self, obj):
        """Get the next upcoming or most recent schedule for this service."""
        from datetime import date

        # Use the already-prefetched schedules to avoid extra DB queries
        all_schedules = list(obj.schedules.all())

        if not all_schedules:
            return None

        today = date.today()

        # Filter in Python to use the prefetch cache
        upcoming = [
            s for s in all_schedules if s.scheduled_date >= today
        ]
        if upcoming:
            upcoming.sort(key=lambda s: (s.scheduled_date, s.scheduled_time or time.min))
            next_schedule = upcoming[0]
        else:
            all_schedules.sort(key=lambda s: (s.scheduled_date, s.scheduled_time or time.min), reverse=True)
            next_schedule = all_schedules[0]

        return {
            'id': next_schedule.id,
            'schedule_type': next_schedule.schedule_type,
            'scheduled_date': next_schedule.scheduled_date,
            'scheduled_time': next_schedule.scheduled_time,
            'status': next_schedule.status,
        }

    def validate(self, data):
        """Validate service data."""
        create_reinstall = data.get("create_reinstall", False)
        if create_reinstall and data.get("service_type") != "dismantle":
            raise ValidationError("Auto-create reinstall is only available for dismantle services.")

        if create_reinstall and not data.get("reinstall_same_address", True):
            if not data.get("reinstall_override_address"):
                raise ValidationError("Reinstall address is required when 'same address' is disabled.")

        # Auto-assign Main stall - services always go to Main stall
        main_stall = get_main_stall()
        if not main_stall:
            raise ValidationError("Main stall not configured in system.")
        data["stall"] = main_stall

        return data

    def create(self, validated_data):
        """
        Create service with appliances, technician assignments, and reserve stock.
        Revenue is calculated but transactions are created on completion.
        Auto-creates Schedule records for field work (home_service, pull_out).
        Supports aircon installation for brand new and second-hand units.
        """
        appliances_data = validated_data.pop("appliances", [])
        technician_assignments_data = validated_data.pop("technician_assignments", [])
        appointment_datetime = validated_data.pop("appointment_datetime", None)
        reinstall_appointment_datetime = validated_data.pop("reinstall_appointment_datetime", None)
        aircon_installation_data = validated_data.pop("aircon_installation_data", None)
        create_reinstall = validated_data.pop("create_reinstall", False)
        reinstall_same_address = validated_data.pop("reinstall_same_address", True)
        reinstall_override_address = validated_data.pop("reinstall_override_address", None)
        reinstall_override_contact_person = validated_data.pop("reinstall_override_contact_person", None)
        reinstall_override_contact_number = validated_data.pop("reinstall_override_contact_number", None)

        if validated_data.get("service_type") == "dismantle" and create_reinstall:
            validated_data["service_leg"] = Service.ServiceLeg.DISMANTLE
        else:
            validated_data["service_leg"] = Service.ServiceLeg.SINGLE

        with transaction.atomic():
            service = Service.objects.create(**validated_data)

            # Handle aircon installation if this is an installation service
            if service.service_type == 'installation' and aircon_installation_data:
                self._create_aircon_installation(service, aircon_installation_data)

            # Create appliances (which reserves stock)
            for appliance_data in appliances_data:
                appliance_data["service"] = service
                serializer = ServiceApplianceSerializer(
                    data=appliance_data,
                    context=self.context
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()

            # Create technician assignments
            technician_ids = []
            for assignment_data in technician_assignments_data:
                # Extract technician (may already be an object from validation)
                technician = assignment_data.get('technician')

                # Handle both cases: technician might be CustomUser object or integer ID
                if isinstance(technician, CustomUser):
                    # Already a CustomUser object from validation
                    pass
                elif isinstance(technician, int):
                    # Integer ID - fetch the object
                    try:
                        technician = CustomUser.objects.get(pk=technician)
                    except CustomUser.DoesNotExist:
                        raise ValidationError(f"Technician with ID {technician} does not exist.")
                else:
                    raise ValidationError(f"Invalid technician value: {technician}")

                # Extract appliance (may also be an object from validation)
                appliance = assignment_data.get('appliance')
                if appliance and not isinstance(appliance, AirconUnit):
                    try:
                        appliance = AirconUnit.objects.get(pk=appliance)
                    except AirconUnit.DoesNotExist:
                        raise ValidationError(f"Appliance with ID {appliance} does not exist.")

                # Create assignment directly
                assignment = TechnicianAssignment.objects.create(
                    service=service,
                    technician=technician,
                    appliance=appliance,
                    assignment_type=assignment_data.get('assignment_type', 'repair'),
                    note=assignment_data.get('note', '')
                )
                technician_ids.append(technician.id)

            # Auto-create Schedule(s) based on service_mode
            self._create_schedules_for_service(service, list(set(technician_ids)), appointment_datetime)

            # Calculate initial revenue (no transactions yet)
            RevenueCalculator.calculate_service_revenue(service, save=True)

            # Auto-create linked reinstall service for dismantle workflow
            if service.service_type == "dismantle" and create_reinstall:
                from utils.enums import ServiceStatus as SvcStatus
                reinstall_service = Service.objects.create(
                    client=service.client,
                    stall=service.stall,
                    service_type="installation",
                    service_mode=service.service_mode,
                    service_leg=Service.ServiceLeg.REINSTALL,
                    linked_parent_service=service,
                    status=SvcStatus.IN_PROGRESS,
                    override_address=(
                        service.override_address
                        if reinstall_same_address
                        else (reinstall_override_address or service.override_address)
                    ),
                    override_contact_person=(
                        service.override_contact_person
                        if reinstall_same_address
                        else (reinstall_override_contact_person or service.override_contact_person)
                    ),
                    override_contact_number=(
                        service.override_contact_number
                        if reinstall_same_address
                        else (reinstall_override_contact_number or service.override_contact_number)
                    ),
                    remarks=f"Auto-created reinstall for dismantle service #{service.id}",
                )

                unique_tech_ids = list(set(technician_ids))
                for tech_id in unique_tech_ids:
                    TechnicianAssignment.objects.create(
                        service=reinstall_service,
                        technician_id=tech_id,
                        assignment_type="repair",
                        note=f"Auto-linked from dismantle service #{service.id}",
                    )

                self._create_schedules_for_service(
                    reinstall_service,
                    unique_tech_ids,
                    reinstall_appointment_datetime,
                )
                RevenueCalculator.calculate_service_revenue(reinstall_service, save=True)

        # Fetch service with related objects for proper serialization
        service = Service.objects.select_related('client', 'stall').prefetch_related(
            'technician_assignments__technician',
            'appliances'
        ).get(pk=service.pk)

        return service

    def update(self, instance, validated_data):
        """Update service, appliances, and technician assignments."""
        appliances_data = validated_data.pop("appliances", None)
        technician_assignments_data = validated_data.pop("technician_assignments", None)
        appointment_datetime = validated_data.pop("appointment_datetime", None)

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            # Update existing schedule date/time if appointment_datetime changed
            if appointment_datetime is not None:
                self._update_schedule_datetime(instance, appointment_datetime)

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

            # Handle technician assignments update if provided
            if technician_assignments_data is not None:
                # Clear existing assignments and create new ones
                instance.technician_assignments.all().delete()
                technician_ids = []
                for assignment_data in technician_assignments_data:
                    # Extract technician (may already be an object from validation)
                    technician = assignment_data.get('technician')

                    # Handle both cases: technician might be CustomUser object or integer ID
                    if isinstance(technician, CustomUser):
                        # Already a CustomUser object from validation
                        pass
                    elif isinstance(technician, int):
                        # Integer ID - fetch the object
                        try:
                            technician = CustomUser.objects.get(pk=technician)
                        except CustomUser.DoesNotExist:
                            raise ValidationError(f"Technician with ID {technician} does not exist.")
                    else:
                        raise ValidationError(f"Invalid technician value: {technician}")

                    # Extract appliance (may also be an object from validation)
                    appliance = assignment_data.get('appliance')
                    if appliance and not isinstance(appliance, AirconUnit):
                        try:
                            appliance = AirconUnit.objects.get(pk=appliance)
                        except AirconUnit.DoesNotExist:
                            raise ValidationError(f"Appliance with ID {appliance} does not exist.")

                    # Create assignment directly
                    assignment = TechnicianAssignment.objects.create(
                        service=instance,
                        technician=technician,
                        appliance=appliance,
                        assignment_type=assignment_data.get('assignment_type', 'repair'),
                        note=assignment_data.get('note', '')
                    )
                    technician_ids.append(technician.id)

                # Update schedules if technicians changed
                if technician_ids:
                    self._update_schedule_technicians(instance, list(set(technician_ids)))

            # Recalculate revenue
            RevenueCalculator.calculate_service_revenue(instance, save=True)

        # Fetch service with related objects for proper serialization
        instance = Service.objects.select_related('client', 'stall').prefetch_related(
            'technician_assignments__technician',
            'appliances'
        ).get(pk=instance.pk)

        return instance

    def _create_aircon_installation(self, service, installation_data):
        """
        Create aircon installation for brand new units.
        Unit sale and payment will be handled during service payment recording.

        Args:
            service: Service instance
            installation_data: Dict with installation details:
                - unit_type: 'brand_new' or 'second_hand'
                - unit_id: (if brand_new) AirconUnit ID
                - labor_fee: Labor fee amount
        """
        from installations.models import AirconInstallation, AirconUnit

        unit_type = installation_data.get('unit_type', 'brand_new')
        labor_fee = Decimal(str(installation_data.get('labor_fee', 0)))

        if unit_type == 'brand_new':
            # Handle brand new unit from inventory
            unit_id = installation_data.get('unit_id')
            if not unit_id:
                raise ValidationError("unit_id is required for brand new installations")

            try:
                unit = AirconUnit.objects.get(id=unit_id)
            except AirconUnit.DoesNotExist:
                raise ValidationError(f"Aircon unit with ID {unit_id} not found")

            # Create installation record
            installation = AirconInstallation.objects.create(
                service=service,
                notes=f"Brand New Unit: {unit.serial_number}, Model: {unit.model}"
            )

            # Link unit to installation
            unit.installation = installation
            unit.save(update_fields=['installation', 'updated_at'])

            # Create service appliance
            appliance = ServiceAppliance.objects.create(
                service=service,
                appliance_type=None,
                brand=unit.model.brand.name if unit.model and unit.model.brand else None,
                model=unit.model.name if unit.model else None,
                serial_number=unit.serial_number,
                labor_fee=labor_fee,
            )
        else:
            # Handle second-hand unit (manual entry) - not currently used in frontend
            brand = installation_data.get('brand')

            if not brand:
                raise ValidationError(
                    "brand is required for second-hand installations"
                )

            # Create installation record
            installation = AirconInstallation.objects.create(
                service=service,
                notes=f"Second-Hand Unit: {brand}"
            )

            # Create service appliance for second-hand unit
            appliance = ServiceAppliance.objects.create(
                service=service,
                appliance_type=None,  # Aircon installation
                brand=brand,
                model="",
                serial_number="",
                labor_fee=labor_fee,
            )

    def _create_schedules_for_service(self, service, technician_ids, appointment_datetime=None):
        """
        Auto-create Schedule records based on service_mode.

        - CARRY_IN: No schedule (customer brings to shop)
        - HOME_SERVICE: 1 schedule for field appointment
        - PULL_OUT: 1 schedule for pickup (delivery scheduled later)
        """
        from datetime import time

        from django.utils import timezone
        from schedules.models import Schedule
        from utils.enums import ServiceMode

        # CARRY_IN: No schedule needed
        if service.service_mode == ServiceMode.CARRY_IN:
            return

        # Get request user for created_by
        request = self.context.get('request')
        created_by = request.user if request and hasattr(request, 'user') else None

        # HOME_SERVICE: Create 1 schedule for the appointment
        if service.service_mode == ServiceMode.HOME_SERVICE:
            if not appointment_datetime:
                return  # No appointment yet — schedule can be created later

            scheduled_date = appointment_datetime.date()
            scheduled_time = appointment_datetime.time()

            schedule = Schedule.objects.create(
                client=service.client,
                service=service,
                schedule_type='home_service',
                scheduled_date=scheduled_date,
                scheduled_time=scheduled_time,
                estimated_duration=60,
                status='pending',
                address=service.override_address or (service.client.address if service.client else ''),
                contact_person=service.override_contact_person or (service.client.full_name if service.client else ''),
                contact_number=service.override_contact_number or (service.client.contact_number if service.client else ''),
                notes=service.description,
                created_by=created_by
            )
            if technician_ids:
                schedule.technicians.set(technician_ids)

        # PULL_OUT: Create 1 schedule for pickup (delivery created later)
        elif service.service_mode == ServiceMode.PULL_OUT:
            if service.pickup_date:
                schedule = Schedule.objects.create(
                    client=service.client,
                    service=service,
                    schedule_type='pull_out',
                    scheduled_date=service.pickup_date,
                    scheduled_time=time(9, 0),  # Default 9 AM
                    estimated_duration=60,
                    status='pending',
                    address=service.override_address or (service.client.address if service.client else ''),
                    contact_person=service.override_contact_person or (service.client.full_name if service.client else ''),
                    contact_number=service.override_contact_number or (service.client.contact_number if service.client else ''),
                    notes=f"Pick up for {service.description}",
                    created_by=created_by
                )
                if technician_ids:
                    schedule.technicians.set(technician_ids)

    def _update_schedule_technicians(self, service, technician_ids):
        """Update technicians assigned to existing schedules for this service."""
        from schedules.models import Schedule

        schedules = Schedule.objects.filter(service=service, status__in=['pending', 'confirmed'])

        for schedule in schedules:
            if technician_ids:
                schedule.technicians.set(technician_ids)

    def _update_schedule_datetime(self, service, appointment_datetime):
        """Update the date/time of pending/confirmed schedules for this service.
        If no schedule exists (e.g. service mode changed to home_service), create one."""
        from schedules.models import Schedule

        schedules = list(Schedule.objects.filter(
            service=service,
            status__in=['pending', 'confirmed'],
        ))

        scheduled_date = appointment_datetime.date()
        scheduled_time = appointment_datetime.time()

        if schedules:
            for schedule in schedules:
                schedule.scheduled_date = scheduled_date
                schedule.scheduled_time = scheduled_time
                # Also update contact/address in case they changed on the service
                schedule.address = (
                    service.override_address
                    or (service.client.address if service.client else '')
                )
                schedule.contact_person = (
                    service.override_contact_person
                    or (service.client.full_name if service.client else '')
                )
                schedule.contact_number = (
                    service.override_contact_number
                    or (service.client.contact_number if service.client else '')
                )
                schedule.save()
        else:
            # No schedule exists yet — create one (e.g. mode changed to home_service)
            from utils.enums import ServiceMode

            if service.service_mode in [ServiceMode.HOME_SERVICE, ServiceMode.PULL_OUT]:
                request = self.context.get('request')
                created_by = request.user if request and hasattr(request, 'user') else None

                schedule_type = (
                    'home_service' if service.service_mode == ServiceMode.HOME_SERVICE
                    else 'pull_out'
                )
                schedule = Schedule.objects.create(
                    client=service.client,
                    service=service,
                    schedule_type=schedule_type,
                    scheduled_date=scheduled_date,
                    scheduled_time=scheduled_time,
                    estimated_duration=60,
                    status='pending',
                    address=service.override_address or (
                        service.client.address if service.client else ''
                    ),
                    contact_person=service.override_contact_person or (
                        service.client.full_name if service.client else ''
                    ),
                    contact_number=service.override_contact_number or (
                        service.client.contact_number if service.client else ''
                    ),
                    notes=service.description,
                    created_by=created_by,
                )
                # Assign existing technicians to the new schedule
                tech_ids = list(
                    service.technician_assignments.values_list(
                        'technician_id', flat=True
                    )
                )
                if tech_ids:
                    schedule.technicians.set(tech_ids)


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
        from utils.enums import ServiceStatus, ServiceType

        service = self.context.get("service")
        if not service:
            raise ValidationError("Service instance required in context.")

        if service.status == ServiceStatus.COMPLETED:
            raise ValidationError("Service is already completed.")

        if service.status == ServiceStatus.CANCELLED:
            raise ValidationError("Cannot complete a cancelled service.")

        # Block completion if any items have pending stock requests
        from services.models import ApplianceItemUsed, ServiceItemUsed
        pending_appliance_items = ApplianceItemUsed.objects.filter(
            appliance__service=service,
            stock_request_status="pending",
        )
        pending_service_items = ServiceItemUsed.objects.filter(
            service=service,
            stock_request_status="pending",
        )
        if pending_appliance_items.exists() or pending_service_items.exists():
            raise ValidationError(
                "Cannot complete service: there are parts with pending stock requests. "
                "Please approve or decline all stock requests first."
            )

        # Block completion if any appliance with parts_needed_notes has unchecked items
        unchecked = service.appliances.filter(
            items_checked=False
        ).exclude(parts_needed_notes="")
        if unchecked.exists():
            names = ", ".join(str(a) for a in unchecked[:3])
            raise ValidationError(
                f"Cannot complete service: items have not been confirmed for: {names}. "
                "All appliance items must be reviewed and confirmed before completing."
            )

        # Block completion if service-level parts are noted but not yet confirmed
        if service.service_parts_needed_notes and not service.service_items_checked:
            raise ValidationError(
                "Cannot complete service: service-level items have not been confirmed. "
                "Please review and confirm the service items before completing."
            )

        # For installation services, ensure parts/items are properly allocated
        if service.service_type == ServiceType.INSTALLATION:
            # Check if any appliance has items added
            has_appliance_items = service.appliances.filter(
                items_used__isnull=False
            ).distinct().exists()

            # Check if there are service-level items
            has_service_items = service.service_items.exists()

            # If no items at all and there are installation units, this is likely an issue
            # (installation services should have either parts, service items, or at minimum parts allocation)
            if not has_appliance_items and not has_service_items and service.installation_units.exists():
                raise ValidationError(
                    "Cannot complete installation service without parts allocation. "
                    "Please ensure all aircon units have been properly configured with parts or cost allocation."
                )

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
        from services.business_logic import cancel_service

        service = self.context.get("service")
        reason = self.validated_data.get("reason", "")

        result = cancel_service(
            service=service,
            reason=reason
        )

        return result


class ServiceReopenSerializer(serializers.Serializer):
    """Serializer for reopening a completed service for revision."""

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Reason for reopening"
    )

    def validate(self, data):
        from utils.enums import ServiceStatus

        service = self.context.get("service")
        if not service:
            raise ValidationError("Service instance required in context.")

        if service.status != ServiceStatus.COMPLETED:
            raise ValidationError("Only completed services can be reopened.")

        return data

    def save(self):
        from services.business_logic import reopen_service

        service = self.context.get("service")
        reason = self.validated_data.get("reason", "")
        user = self.context.get("request").user if self.context.get("request") else None

        return reopen_service(service=service, reason=reason, user=user)


class ServiceRefundRequestSerializer(serializers.Serializer):
    """
    Serializer for processing a service refund.

    Only for completed services where parts are already used.
    """

    refund_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount to refund"
    )
    reason = serializers.CharField(
        help_text="Reason for refund"
    )
    refund_type = serializers.ChoiceField(
        choices=[('full', 'Full Refund'), ('partial', 'Partial Refund')],
        default='partial'
    )
    refund_method = serializers.ChoiceField(
        choices=[
            ('cash', 'Cash'),
            ('gcash', 'GCash'),
            ('bank_transfer', 'Bank Transfer'),
        ],
        default='cash'
    )

    def validate(self, data):
        """Validate refund can be processed."""
        from utils.enums import ServiceStatus

        service = self.context.get("service")
        if not service:
            raise ValidationError("Service instance required in context.")

        if service.status != ServiceStatus.COMPLETED:
            raise ValidationError(
                "Can only process refunds for completed services. "
                "Use cancel endpoint for incomplete services."
            )

        return data

    def save(self):
        """Execute service refund workflow."""
        from services.business_logic import ServicePaymentManager

        service = self.context.get("service")
        user = self.context.get("request").user if self.context.get("request") else None

        result = ServicePaymentManager.refund_service(
            service=service,
            refund_amount=self.validated_data['refund_amount'],
            reason=self.validated_data['reason'],
            refund_type=self.validated_data['refund_type'],
            refund_method=self.validated_data['refund_method'],
            processed_by=user
        )

        return result


# ----------------------------------
# Service Payment Serializers
# ----------------------------------
class ServicePaymentSerializer(serializers.ModelSerializer):
    """Serializer for ServicePayment model."""

    received_by_name = serializers.CharField(
        source="received_by.get_full_name", read_only=True
    )
    payment_type_display = serializers.CharField(
        source="get_payment_type_display", read_only=True
    )
    cheque_number = serializers.CharField(
        source="cheque_collection.cheque_number", read_only=True
    )

    class Meta:
        model = ServicePayment
        fields = [
            "id",
            "service",
            "payment_type",
            "payment_type_display",
            "amount",
            "payment_date",
            "received_by",
            "received_by_name",
            "cheque_collection",
            "cheque_number",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ServiceRefundSerializer(serializers.ModelSerializer):
    """Serializer for ServiceRefund model."""

    processed_by_name = serializers.CharField(
        source="processed_by.get_full_name", read_only=True, allow_null=True
    )
    refund_type_display = serializers.CharField(
        source="get_refund_type_display", read_only=True
    )
    refund_method_display = serializers.CharField(
        source="get_refund_method_display", read_only=True
    )

    class Meta:
        model = ServiceRefund
        fields = [
            "id",
            "service",
            "refund_amount",
            "refund_type",
            "refund_type_display",
            "reason",
            "refund_date",
            "processed_by",
            "processed_by_name",
            "refund_method",
            "refund_method_display",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "refund_date", "created_at"]


class CreateServicePaymentSerializer(serializers.Serializer):
    """Serializer for creating a service payment."""

    payment_type = serializers.ChoiceField(choices=PaymentType.choices)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    payment_date = serializers.DateTimeField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Override payment date for backdating. If not provided and service has transaction_date, payment is auto-backdated.",
    )
    cheque_collection = serializers.PrimaryKeyRelatedField(
        queryset=ChequeCollection.objects.all(),
        required=False,
        allow_null=True,
        default=None,
        help_text="Linked cheque collection ID (for cheque payments)",
    )

    def validate_amount(self, value):
        """Validate payment amount is positive."""
        if value <= 0:
            raise ValidationError("Payment amount must be greater than zero.")
        return value

    def validate_cheque_collection(self, value):
        """Validate cheque is not already linked to another payment."""
        if value is not None:
            # Check if cheque is already linked to a service payment
            if value.service_payments.exists():
                raise ValidationError(
                    "This cheque is already linked to another service payment."
                )
            # Check if cheque is already linked to a sales payment
            if value.sales_payments.exists():
                raise ValidationError(
                    "This cheque is already linked to a sales payment."
                )
        return value

    def validate(self, data):
        """Validate payment doesn't exceed balance due."""
        service = self.context.get("service")
        if not service:
            raise ValidationError("Service context is required.")

        amount = data["amount"]
        balance_due = service.balance_due

        if amount > balance_due:
            raise ValidationError(
                f"Payment amount (₱{amount}) exceeds balance due (₱{balance_due}). "
                f"Total revenue: ₱{service.total_revenue}, Already paid: ₱{service.total_paid}"
            )

        # Validate cheque is provided for cheque payment type
        if data["payment_type"] == "cheque" and not data.get("cheque_collection"):
            raise ValidationError(
                "A cheque collection must be selected for cheque payments."
            )

        return data

    def save(self):
        """Create the service payment."""
        from services.business_logic import ServicePaymentManager

        service = self.context.get("service")
        user = self.context.get("request").user if self.context.get("request") else None

        payment = ServicePaymentManager.create_payment(
            service=service,
            payment_type=self.validated_data["payment_type"],
            amount=self.validated_data["amount"],
            received_by=user,
            notes=self.validated_data.get("notes", ""),
            cheque_collection=self.validated_data.get("cheque_collection"),
            payment_date=self.validated_data.get("payment_date"),
        )

        return payment


class ServicePaymentSummarySerializer(serializers.Serializer):
    """Serializer for service payment summary."""

    service_id = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    balance_due = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_status = serializers.CharField()
    payments = ServicePaymentSerializer(many=True)


class JobOrderTemplatePrintSerializer(serializers.ModelSerializer):
    """Serializer for job order template print tracking."""

    printed_by_name = serializers.CharField(
        source="printed_by.get_full_name", read_only=True
    )

    class Meta:
        model = JobOrderTemplatePrint
        fields = [
            "id",
            "start_number",
            "end_number",
            "printed_by",
            "printed_by_name",
            "printed_at",
        ]
        read_only_fields = ["id", "printed_by", "printed_by_name", "printed_at"]

    def validate(self, attrs):
        if attrs["start_number"] > attrs["end_number"]:
            raise ValidationError(
                "Start number must be less than or equal to end number."
            )
        if attrs["end_number"] - attrs["start_number"] + 1 > 200:
            raise ValidationError("Cannot print more than 200 templates at a time.")
        return attrs


class ServicePartTemplateLineSerializer(serializers.ModelSerializer):
    item_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ServicePartTemplateLine
        fields = [
            "id",
            "item",
            "item_name",
            "custom_description",
            "custom_price",
            "quantity",
            "sort_order",
        ]
        read_only_fields = ["id"]

    def get_item_name(self, obj):
        if obj.item:
            return obj.item.name
        return obj.custom_description

    def validate(self, attrs):
        item = attrs.get("item")
        custom_description = (attrs.get("custom_description") or "").strip()
        custom_price = attrs.get("custom_price")

        if not item and not custom_description:
            raise ValidationError("Each line requires either an inventory item or a custom description.")

        if item and custom_description:
            attrs["custom_description"] = ""
            attrs["custom_price"] = None
            return attrs

        if not item and custom_price is None:
            raise ValidationError("Custom lines require a custom price.")

        return attrs


class ServicePartTemplateSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    lines = ServicePartTemplateLineSerializer(many=True)

    class Meta:
        model = ServicePartTemplate
        fields = [
            "id",
            "name",
            "description",
            "lines",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None

    def validate_lines(self, value):
        if not value:
            raise ValidationError("At least one template line is required.")
        return value

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            validated_data["created_by"] = request.user

        template = ServicePartTemplate.objects.create(**validated_data)
        ServicePartTemplateLine.objects.bulk_create(
            [
                ServicePartTemplateLine(template=template, **line)
                for line in lines_data
            ]
        )
        return ServicePartTemplate.objects.prefetch_related("lines").get(pk=template.pk)

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lines", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if lines_data is not None:
            instance.lines.all().delete()
            ServicePartTemplateLine.objects.bulk_create(
                [
                    ServicePartTemplateLine(template=instance, **line)
                    for line in lines_data
                ]
            )

        return ServicePartTemplate.objects.prefetch_related("lines").get(pk=instance.pk)


# ----------------------------------
# Company Asset Serializer
# ----------------------------------
class CompanyAssetSerializer(serializers.ModelSerializer):
    service_ref = serializers.SerializerMethodField()
    client_name = serializers.SerializerMethodField()
    sold_to_name = serializers.SerializerMethodField()
    declared_by_name = serializers.CharField(
        source="acquired_by.get_full_name", read_only=True, allow_null=True
    )

    class Meta:
        model = CompanyAsset
        fields = [
            "id",
            "service",
            "service_ref",
            "client_name",
            "service_appliance",
            "appliance_description",
            "acquisition_type",
            "acquisition_price",
            # Complementary / warranty tracking
            "is_complementary",
            "complementary_reason",
            "acquired_at",
            "acquired_by",
            "declared_by_name",
            "condition_notes",
            "status",
            "disposed_at",
            "disposal_notes",
            "sale_price",
            "sold_to",
            "sold_to_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "acquired_at",
            "created_at",
            "updated_at",
        ]

    def get_service_ref(self, obj):
        return f"SVC-{obj.service_id}"

    def get_client_name(self, obj):
        try:
            return obj.service.client.full_name
        except Exception:
            return None

    def get_sold_to_name(self, obj):
        try:
            return obj.sold_to.full_name if obj.sold_to else None
        except Exception:
            return None
