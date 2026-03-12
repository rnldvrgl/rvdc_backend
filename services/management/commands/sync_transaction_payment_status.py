"""
One-time command to sync SalesTransaction.payment_status with the linked
Service.payment_status for all service-related transactions.

Run after deploying the update_payment_status sync fix:
    python manage.py sync_transaction_payment_status
"""

from django.core.management.base import BaseCommand

from sales.models import SalesTransaction
from services.models import Service


class Command(BaseCommand):
    help = "Sync payment_status from Service to linked SalesTransaction records"

    def handle(self, *args, **options):
        updated = 0
        services = (
            Service.objects.exclude(
                related_transaction__isnull=True,
                related_sub_transaction__isnull=True,
            )
            .select_related("related_transaction", "related_sub_transaction")
        )

        for svc in services:
            txns = []
            if svc.related_transaction_id:
                txns.append(svc.related_transaction)
            if svc.related_sub_transaction_id:
                txns.append(svc.related_sub_transaction)

            for tx in txns:
                if tx.payment_status != svc.payment_status:
                    old = tx.payment_status
                    tx.payment_status = svc.payment_status
                    tx.save(update_fields=["payment_status"])
                    updated += 1
                    self.stdout.write(
                        f"  Service #{svc.id}: TX #{tx.id} "
                        f"{old} -> {svc.payment_status}"
                    )

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. Updated {updated} transaction(s).")
        )
