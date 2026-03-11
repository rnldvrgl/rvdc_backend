from decimal import Decimal
from rest_framework import serializers
from remittances.models import RemittanceRecord, CashDenominationBreakdown
from inventory.models import Stall
from sales.models import SalesPayment, PaymentStatus
from expenses.models import Expense
from django.db.models import Sum
from django.utils import timezone


class CashDenominationBreakdownSerializer(serializers.ModelSerializer):
    total_remitted_amount = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    total_declared_amount = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2, source="total_cash_declared"
    )
    cod_amount = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    total_cash_declared = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )

    class Meta:
        model = CashDenominationBreakdown
        exclude = ["id", "remittance"]


class StallSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class RemittanceRecordSerializer(serializers.ModelSerializer):
    cash_breakdown = CashDenominationBreakdownSerializer(required=False)
    stall = serializers.PrimaryKeyRelatedField(queryset=Stall.objects.all())
    stall_data = serializers.SerializerMethodField()
    remitted_by = serializers.SerializerMethodField()
    expected_remittance = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    total_collected = serializers.DecimalField(
        read_only=True, max_digits=10, decimal_places=2
    )
    is_remitted = serializers.BooleanField(read_only=True)
    cod_for_next_day = serializers.SerializerMethodField()
    cod_for_today = serializers.SerializerMethodField()

    # Optional: allow backdating remittances (admin fills in past dates)
    remittance_date = serializers.DateField(
        required=False, write_only=True, allow_null=True,
        help_text="If provided, creates remittance for this date instead of today. "
                  "Sales & expenses will be pulled from this date."
    )
    # Optional: immediately acknowledge a backdated remittance
    mark_as_acknowledged = serializers.BooleanField(
        required=False, write_only=True, default=False,
        help_text="If true, marks the new remittance as acknowledged on creation."
    )

    # Optional: manual overrides for sales totals (use instead of auto-computed)
    override_sales_cash = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, write_only=True, allow_null=True,
    )
    override_sales_gcash = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, write_only=True, allow_null=True,
    )
    override_sales_credit = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, write_only=True, allow_null=True,
    )
    override_sales_debit = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, write_only=True, allow_null=True,
    )
    override_sales_cheque = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, write_only=True, allow_null=True,
    )
    override_expenses = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, write_only=True, allow_null=True,
    )

    class Meta:
        model = RemittanceRecord
        fields = [
            "id",
            "stall",
            "stall_data",
            "total_sales_cash",
            "total_sales_gcash",
            "total_sales_credit",
            "total_sales_debit",
            "total_sales_cheque",
            "total_expenses",
            "manually_adjusted",
            "remitted_amount",
            "declared_amount",
            "remitted_by",
            "is_remitted",
            "created_at",
            "notes",
            "cash_breakdown",
            "expected_remittance",
            "total_collected",
            "balance",
            "cod_for_next_day",
            "cod_for_today",
            "remittance_date",
            "mark_as_acknowledged",
            "override_sales_cash",
            "override_sales_gcash",
            "override_sales_credit",
            "override_sales_debit",
            "override_sales_cheque",
            "override_expenses",
        ]
        read_only_fields = ["manually_adjusted"]

    def get_stall_data(self, obj):
        return {"id": obj.stall.id, "name": obj.stall.name} if obj.stall else None

    def get_remitted_by(self, obj):
        if obj.remitted_by:
            return {
                "id": obj.remitted_by.id,
                "full_name": obj.remitted_by.get_full_name(),
            }
        return None

    def get_expected_remittance(self, obj):
        return obj.expected_remittance or Decimal("0.00")

    def get_balance(self, obj):
        return obj.balance or Decimal("0.00")

    def get_cod_for_next_day(self, obj):
        return getattr(obj.cash_breakdown, "cod_amount", 0)

    def get_cod_for_today(self, obj):
        # Use the remittance's own date to look up COD from the day before
        if obj.created_at:
            return RemittanceRecord.get_cod_for_date(obj.stall, obj.created_at.date())
        return RemittanceRecord.get_cod_for_today(obj.stall)

    @staticmethod
    def is_empty_breakdown(data: dict) -> bool:
        fields = [
            "count_1000",
            "count_500",
            "count_200",
            "count_100",
            "count_50",
            "count_20",
            "count_10",
            "count_5",
            "count_1",
            "declared_count_1000",
            "declared_count_500",
            "declared_count_200",
            "declared_count_100",
            "declared_count_50",
            "declared_count_20",
            "declared_count_10",
            "declared_count_5",
            "declared_count_1",
        ]
        return all(data.get(field) in [None, 0] for field in fields)

    def validate(self, attrs):
        breakdown = attrs.get("cash_breakdown")
        if breakdown and self.is_empty_breakdown(breakdown):
            raise serializers.ValidationError(
                {"cash_breakdown": "At least one denomination must be provided."}
            )

        user = self.context["request"].user

        # Non-admin users can only remit for their assigned stall
        if user.role != "admin":
            stall = attrs.get("stall")
            if stall and user.assigned_stall and stall != user.assigned_stall:
                raise serializers.ValidationError(
                    {"stall": "You can only create remittances for your assigned stall."}
                )
            # Non-admin cannot backdate or auto-acknowledge
            if attrs.get("remittance_date"):
                raise serializers.ValidationError(
                    {"remittance_date": "Only administrators can backdate remittances."}
                )
            if attrs.get("mark_as_acknowledged"):
                raise serializers.ValidationError(
                    {"mark_as_acknowledged": "Only administrators can mark remittances as acknowledged."}
                )

        return attrs

    def create(self, validated_data):
        breakdown_data = validated_data.pop("cash_breakdown", None)
        stall = validated_data.pop("stall")
        user = self.context["request"].user
        notes = validated_data.pop("notes", "")
        remittance_date = validated_data.pop("remittance_date", None)
        mark_as_acknowledged = validated_data.pop("mark_as_acknowledged", False)

        # Extract manual overrides
        overrides = {
            k.replace("override_sales_", ""): validated_data.pop(k)
            for k in list(validated_data.keys())
            if k.startswith("override_sales_") and validated_data.get(k) is not None
        }
        override_expenses = validated_data.pop("override_expenses", None)
        # Clean remaining override keys
        for k in [k for k in validated_data if k.startswith("override_")]:
            validated_data.pop(k)

        manually_adjusted = bool(overrides) or override_expenses is not None

        # Use provided date or default to today
        target_date = remittance_date or timezone.localdate()

        # 🚫 Prevent multiple remittances per stall per day
        if RemittanceRecord.objects.filter(
            stall=stall, created_at__date=target_date
        ).exists():
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        f"A remittance already exists for this stall on {target_date.strftime('%b %d, %Y')}."
                    ]
                }
            )

        # 💰 Compute sales by payment type for the target date
        total_sales = {
            pt: self._sum_sales(stall, target_date, pt)
            for pt in ["cash", "gcash", "credit", "debit", "cheque"]
        }
        # Apply manual overrides (replace system-computed values)
        for pt, val in overrides.items():
            total_sales[pt] = val

        # 📉 Get total expenses for the target date
        total_expenses = (
            Expense.objects.filter(stall=stall, created_at__date=target_date).aggregate(
                total=Sum("paid_amount")
            )["total"]
            or 0
        )
        if override_expenses is not None:
            total_expenses = override_expenses

        # 💵 Compute totals from breakdown
        remitted_amt = self._compute_total(breakdown_data, declared=False)
        declared_amt = self._compute_total(breakdown_data, declared=True)

        # 📅 Set created_at: use noon of target date for backdated, or now for today
        if remittance_date:
            from datetime import datetime, time
            created_at = timezone.make_aware(
                datetime.combine(remittance_date, time(12, 0))
            )
        else:
            created_at = timezone.now()

        # 🧾 Create the record
        remittance = RemittanceRecord.objects.create(
            stall=stall,
            remitted_by=user,
            created_at=created_at,
            notes=notes,
            remitted_amount=remitted_amt,
            declared_amount=declared_amt,
            total_expenses=total_expenses,
            is_remitted=bool(mark_as_acknowledged),
            manually_adjusted=manually_adjusted,
            **{f"total_sales_{k}": v for k, v in total_sales.items()},
        )

        if breakdown_data:
            CashDenominationBreakdown.objects.create(
                remittance=remittance, **breakdown_data
            )

        return remittance

    def update(self, instance, validated_data):
        breakdown_data = validated_data.pop("cash_breakdown", None)
        # Remove write-only fields that don't apply to updates
        validated_data.pop("remittance_date", None)
        validated_data.pop("mark_as_acknowledged", None)

        # Map override fields → model fields
        sales_field_map = {
            "override_sales_cash": "total_sales_cash",
            "override_sales_gcash": "total_sales_gcash",
            "override_sales_credit": "total_sales_credit",
            "override_sales_debit": "total_sales_debit",
            "override_sales_cheque": "total_sales_cheque",
            "override_expenses": "total_expenses",
        }
        has_override = False
        for override_key, model_field in sales_field_map.items():
            val = validated_data.pop(override_key, None)
            if val is not None:
                validated_data[model_field] = val
                has_override = True
        # Clean any remaining override keys
        for k in [k for k in validated_data if k.startswith("override_")]:
            validated_data.pop(k)

        if has_override:
            validated_data["manually_adjusted"] = True

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if breakdown_data:
            if self.is_empty_breakdown(breakdown_data):
                raise serializers.ValidationError(
                    {"cash_breakdown": "At least one denomination must be provided."}
                )

            breakdown, _ = CashDenominationBreakdown.objects.get_or_create(
                remittance=instance
            )
            for attr, value in breakdown_data.items():
                setattr(breakdown, attr, value)
            breakdown.save()

            instance.remitted_amount = self._compute_total(
                breakdown_data, declared=False
            )
            instance.declared_amount = self._compute_total(
                breakdown_data, declared=True
            )
            instance.save()

        return instance

    def _sum_sales(self, stall, date_val, payment_type: str):
        # Sum all payments of this type for paid/partial transactions on this date
        total_payments = SalesPayment.objects.filter(
            transaction__stall=stall,
            payment_date__date=date_val,
            transaction__payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
            transaction__voided=False,
            transaction__is_deleted=False,
            payment_type=payment_type,
        ).aggregate(total=Sum("amount"))["total"] or 0

        # Change is always given in cash, so only subtract from cash totals.
        # Subtract once per transaction (not per payment) to avoid double-counting.
        if payment_type == "cash":
            from sales.models import SalesTransaction
            total_change = SalesTransaction.objects.filter(
                stall=stall,
                payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                voided=False,
                is_deleted=False,
                payments__payment_date__date=date_val,
            ).distinct().aggregate(
                total=Sum("change_amount")
            )["total"] or 0
            return total_payments - total_change

        return total_payments

    def _compute_total(self, data: dict, declared=False) -> int:
        if not data:
            return 0
        keys = [
            (1000, "declared_count_1000" if declared else "count_1000"),
            (500, "declared_count_500" if declared else "count_500"),
            (200, "declared_count_200" if declared else "count_200"),
            (100, "declared_count_100" if declared else "count_100"),
            (50, "declared_count_50" if declared else "count_50"),
            (20, "declared_count_20" if declared else "count_20"),
            (10, "declared_count_10" if declared else "count_10"),
            (5, "declared_count_5" if declared else "count_5"),
            (1, "declared_count_1" if declared else "count_1"),
        ]
        return sum((data.get(field, 0) or 0) * denom for denom, field in keys)
