from rest_framework import serializers
from receivables.models import ChequeCollection


class ChequeCollectionSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.full_name", read_only=True)
    collected_by_name = serializers.CharField(
        source="collected_by.get_full_name", read_only=True
    )

    class Meta:
        model = ChequeCollection
        fields = [
            "id",
            "date_collected",
            "client",
            "client_name",
            "issued_by",
            "billing_amount",
            "cheque_amount",
            "cheque_number",
            "cheque_date",
            "bank_name",
            "deposit_bank",
            "or_number",
            "sales_transaction",
            "collection_type",
            "collected_by",
            "collected_by_name",
            "notes",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
            "client_name",
            "collected_by_name",
        ]

    def validate_cheque_number(self, value):
        """
        Ensure cheque number is unique for the same bank and cheque date.
        This avoids duplicates for the same actual cheque.
        """
        bank_name = self.initial_data.get("bank_name")
        cheque_date = self.initial_data.get("cheque_date")

        # Exclude current instance for updates
        qs = ChequeCollection.objects.filter(
            cheque_number=value, bank_name=bank_name, cheque_date=cheque_date
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "A cheque with this number, bank, and date already exists."
            )
        return value
