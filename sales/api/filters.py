from django_filters import rest_framework as filters
from django.db.models import Q
from sales.models import SalesTransaction


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """Supports comma-separated values, e.g. ?payment_status=unpaid,partial"""

    pass


class SalesTransactionFilter(filters.FilterSet):
    payment_status = CharInFilter(field_name="payment_status", lookup_expr="in")
    has_receipt = filters.CharFilter(method="filter_has_receipt")
    receipt_type = filters.CharFilter(method="filter_receipt_type")

    def _get_linked_receipt_txn_ids_by_type(self):
        from services.models import Service

        service_receipt_qs = Service.objects.filter(
            receipts__receipt_number__isnull=False,
        ).exclude(receipts__receipt_number="")

        txn_ids_by_type = {
            "or": set(),
            "si": set(),
        }

        for doc_type in ("or", "si"):
            ids = set(
                service_receipt_qs.filter(receipts__document_type=doc_type).values_list(
                    "related_transaction_id", flat=True
                )
            ) | set(
                service_receipt_qs.filter(receipts__document_type=doc_type).values_list(
                    "related_sub_transaction_id", flat=True
                )
            )
            ids.discard(None)
            txn_ids_by_type[doc_type] = ids

        return txn_ids_by_type

    def filter_has_receipt(self, queryset, name, value):
        txn_ids_by_type = self._get_linked_receipt_txn_ids_by_type()
        linked_txn_ids = txn_ids_by_type["or"] | txn_ids_by_type["si"]

        has_direct_receipt_q = Q(manual_receipt_number__isnull=False) & ~Q(
            manual_receipt_number=""
        )
        has_linked_service_receipt_q = Q(id__in=list(linked_txn_ids))
        has_any_receipt_q = has_direct_receipt_q | has_linked_service_receipt_q

        if value == "with":
            return queryset.filter(has_any_receipt_q).distinct()
        elif value == "without":
            return queryset.exclude(has_any_receipt_q).distinct()
        return queryset

    def filter_receipt_type(self, queryset, name, value):
        values = [v.strip() for v in (value or "").split(",") if v.strip()]
        if not values:
            return queryset

        txn_ids_by_type = self._get_linked_receipt_txn_ids_by_type()
        linked_ids = set()
        for v in values:
            linked_ids |= txn_ids_by_type.get(v, set())

        has_direct_type_q = Q(document_type__in=values)
        has_linked_type_q = Q(id__in=list(linked_ids)) if linked_ids else Q(pk__in=[])
        return queryset.filter(has_direct_type_q | has_linked_type_q).distinct()

    class Meta:
        model = SalesTransaction
        fields = [
            "stall",
            "client",
            "payment_status",
            "voided",
            "transaction_type",
            "receipt_type",
        ]
