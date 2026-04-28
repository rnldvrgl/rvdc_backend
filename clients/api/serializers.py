from rest_framework import serializers
from clients.models import Client, ClientFundDeposit


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = "__all__"


class ClientFundDepositSerializer(serializers.ModelSerializer):
    """Serializer for creating and listing client fund deposits."""

    payment_method_display = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )
    recorded_by_name = serializers.CharField(
        source="recorded_by.get_full_name", read_only=True, allow_null=True
    )
    client_name = serializers.CharField(
        source="client.full_name", read_only=True
    )

    class Meta:
        model = ClientFundDeposit
        fields = [
            "id",
            "client",
            "client_name",
            "amount",
            "deposit_date",
            "payment_method",
            "payment_method_display",
            "notes",
            "recorded_by",
            "recorded_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at", "updated_at"]

    def validate_amount(self, value):
        """Validate deposit amount is positive."""
        if value <= 0:
            raise serializers.ValidationError(
                "Deposit amount must be greater than zero."
            )
        return value

    def create(self, validated_data):
        """Create deposit and atomically credit client fund balance."""
        from django.db import transaction
        from django.db.models import F
        from clients.models import Client

        request = self.context.get("request")
        user = request.user if request else None

        with transaction.atomic():
            deposit = ClientFundDeposit.objects.create(
                **validated_data,
                recorded_by=user,
            )
            Client.objects.filter(pk=deposit.client_id).update(
                fund_balance=F("fund_balance") + deposit.amount
            )

        return deposit


class ClientDetailSerializer(serializers.ModelSerializer):
    """Detailed client serializer with fund information."""

    fund_deposits = ClientFundDepositSerializer(
        source="fund_deposits.all", many=True, read_only=True
    )
    total_fund_received = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id",
            "full_name",
            "contact_number",
            "province",
            "city",
            "barangay",
            "address",
            "fund_balance",
            "total_fund_received",
            "fund_deposits",
            "is_blocklisted",
            "created_at",
            "updated_at",
        ]

    def get_total_fund_received(self, obj):
        """Calculate total fund received from all deposits."""
        from django.db.models import Sum
        total = obj.fund_deposits.aggregate(total=Sum('amount'))['total']
        return total or 0
