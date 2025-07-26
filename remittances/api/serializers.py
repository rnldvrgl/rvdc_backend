from rest_framework import serializers
from remittances.models import RemittanceRecord, CashDenominationBreakdown
from inventory.models import Stall
from sales.models import SalesPayment, PaymentStatus
from expenses.models import Expense
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from datetime import date


class CashDenominationBreakdownSerializer(serializers.ModelSerializer):
    total_remitted_amount = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    cod_amount = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    total_cash_declared = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    coins_remitted = serializers.BooleanField(default=True)

    class Meta:
        model = CashDenominationBreakdown
        exclude = ["id", "remittance"]


class StallSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class RemittanceRecordSerializer(serializers.ModelSerializer):
    cash_breakdown = CashDenominationBreakdownSerializer(required=False)
    stall = serializers.PrimaryKeyRelatedField(queryset=Stall.objects.all())
    stall_data = serializers.SerializerMethodField(read_only=True)
    remitted_by = serializers.SerializerMethodField()
    expected_remittance = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    total_collected = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    balance = serializers.DecimalField(read_only=True, max_digits=10, decimal_places=2)
    is_remitted = serializers.BooleanField(read_only=True)

    class Meta:
        model = RemittanceRecord
        fields = [
            "id",
            "stall",
            "stall_data",
            "date",
            "total_sales_cash",
            "total_sales_gcash",
            "total_sales_credit",
            "total_sales_debit",
            "total_sales_cheque",
            "total_expenses",
            "remitted_amount",
            "remitted_by",
            "is_remitted",
            "created_at",
            "notes",
            "cash_breakdown",
            "expected_remittance",
            "total_collected",
            "balance",
        ]

    @staticmethod
    def is_empty_breakdown(data: dict) -> bool:
        denomination_keys = [
            "count_1000",
            "count_500",
            "count_100",
            "count_50",
            "count_20",
            "count_10",
            "count_5",
            "count_1",
        ]
        return all(data.get(k, 0) in [None, 0] for k in denomination_keys)

    def validate(self, attrs):
        breakdown_data = attrs.get("cash_breakdown")
        if breakdown_data and self.is_empty_breakdown(breakdown_data):
            raise serializers.ValidationError(
                {"cash_breakdown": "Cash breakdown cannot be entirely empty."}
            )
        return attrs

    def get_stall_data(self, obj):
        return {"id": obj.stall.id, "name": obj.stall.name} if obj.stall else None

    def get_remitted_by(self, obj):
        if obj.remitted_by:
            return {
                "id": obj.remitted_by.id,
                "full_name": obj.remitted_by.get_full_name(),
            }
        return None

    def create(self, validated_data):
        breakdown_data = validated_data.pop("cash_breakdown", None)
        notes = validated_data.pop("notes", "")
        stall = validated_data.pop("stall")
        date_val = validated_data.pop("date", date.today())
        user = self.context["request"].user

        def sum_sales(payment_type: str):
            qs = SalesPayment.objects.filter(
                transaction__stall=stall,
                transaction__created_at__date=date_val,
                transaction__payment_status__in=[
                    PaymentStatus.PAID,
                    PaymentStatus.PARTIAL,
                ],
                payment_type=payment_type,
            ).annotate(
                net_amount=ExpressionWrapper(
                    F("amount") - F("transaction__change_amount"),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )
            return qs.aggregate(total=Sum("net_amount"))["total"] or 0

        total_sales_cash = sum_sales("cash")
        total_sales_gcash = sum_sales("gcash")
        total_sales_credit = sum_sales("credit")
        total_sales_debit = sum_sales("debit")
        total_sales_cheque = sum_sales("cheque")

        total_expenses = (
            Expense.objects.filter(stall=stall, created_at__date=date_val).aggregate(
                total=Sum("paid_amount")
            )["total"]
            or 0
        )

        coins_remitted = (
            breakdown_data.get("coins_remitted", True) if breakdown_data else True
        )
        remitted_amount = (
            CashDenominationBreakdown.compute_total_from_counts(
                breakdown_data, coins_remitted=coins_remitted
            )
            if breakdown_data
            else 0
        )

        remittance = RemittanceRecord.objects.create(
            stall=stall,
            total_sales_cash=total_sales_cash,
            total_sales_gcash=total_sales_gcash,
            total_sales_credit=total_sales_credit,
            total_sales_debit=total_sales_debit,
            total_sales_cheque=total_sales_cheque,
            total_expenses=total_expenses,
            remitted_amount=remitted_amount,
            remitted_by=user,
            notes=notes,
        )

        if breakdown_data:
            CashDenominationBreakdown.objects.create(
                remittance=remittance, **breakdown_data
            )

        return remittance

    def update(self, instance, validated_data):
        breakdown_data = validated_data.pop("cash_breakdown", None)

        # Update main fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Only update cash_breakdown if present
        if breakdown_data:
            if self.is_empty_breakdown(breakdown_data):
                raise serializers.ValidationError(
                    {"cash_breakdown": "Cash breakdown cannot be entirely empty."}
                )

            coins_remitted = breakdown_data.get("coins_remitted", True)
            breakdown, _ = CashDenominationBreakdown.objects.get_or_create(
                remittance=instance
            )

            for attr, value in breakdown_data.items():
                setattr(breakdown, attr, value)
            breakdown.save()

            instance.remitted_amount = (
                CashDenominationBreakdown.compute_total_from_counts(
                    breakdown_data, coins_remitted=coins_remitted
                )
            )
            instance.save()

        return instance

    def get_balance(self, obj):
        return obj.total_collected - obj.total_expenses
