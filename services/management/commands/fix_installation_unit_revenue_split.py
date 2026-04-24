"""
Management command to fix installation unit revenue split retroactively.
Also fixes linked service sales transaction types in the same run.

Usage:
    python manage.py fix_installation_unit_revenue_split --date 2026-04-01
    python manage.py fix_installation_unit_revenue_split --date 2026-04-01 --dry-run
"""
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from sales.models import DocumentType, SalesPayment, SalesTransaction, TransactionType
from services.business_logic import ServicePaymentManager, get_sub_stall
from services.models import Service
from utils.enums import ServiceStatus


class Command(BaseCommand):
    help = (
        "Fix installation unit revenue split retroactively for services from a given date "
        "and update linked sales transaction types to 'service'."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            required=True,
            help='Date from which to fix services (format: YYYY-MM-DD). All services on/after this date will be processed.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--service-id',
            type=int,
            help='Fix only a specific service ID (for testing)',
        )

    def _ensure_sub_transaction(self, service, main_tx, dry_run):
        sub_stall = get_sub_stall()
        if not sub_stall:
            raise CommandError("Sub stall is not configured in system settings.")

        if service.related_sub_transaction_id:
            try:
                candidate = service.related_sub_transaction
                if not candidate.voided and candidate.stall_id == sub_stall.id:
                    return candidate, False

                # Cleanup malformed linked sub TX from older buggy runs
                # (e.g., linked to main stall with zero items/payments).
                if (
                    not dry_run
                    and candidate
                    and not candidate.voided
                    and candidate.stall_id != sub_stall.id
                    and not candidate.items.exists()
                    and not candidate.payments.exists()
                ):
                    service.related_sub_transaction = None
                    service.save(update_fields=['related_sub_transaction'])
                    candidate.delete()
            except SalesTransaction.DoesNotExist:
                pass

        if dry_run:
            return None, True

        sub_tx = SalesTransaction.objects.create(
            stall=sub_stall,
            client=service.client,
            sales_clerk=main_tx.sales_clerk if main_tx else None,
            transaction_type=TransactionType.SERVICE,
            document_type=DocumentType.SALES_INVOICE,
            with_2307=False,
        )
        service.related_sub_transaction = sub_tx
        service.save(update_fields=['related_sub_transaction'])
        return sub_tx, True

    def _rebalance_service_payments(self, service, main_tx, sub_tx, dry_run):
        service_payments = list(service.payments.order_by('payment_date'))
        if not service_payments:
            return 0

        main_total = main_tx.computed_total or Decimal('0')
        sub_total = sub_tx.computed_total or Decimal('0')
        main_filled = Decimal('0')
        sub_filled = Decimal('0')

        if not dry_run:
            with transaction.atomic():
                main_tx.payments.all().delete()
                sub_tx.payments.all().delete()

        for service_payment in service_payments:
            m_share, s_share = ServicePaymentManager._waterfall_split(
                service_payment.amount,
                main_total - main_filled,
                sub_total - sub_filled,
            )

            if not dry_run:
                if s_share > 0:
                    SalesPayment.objects.create(
                        transaction=sub_tx,
                        payment_type=service_payment.payment_type,
                        amount=s_share,
                        payment_date=service_payment.payment_date,
                    )
                if m_share > 0:
                    SalesPayment.objects.create(
                        transaction=main_tx,
                        payment_type=service_payment.payment_type,
                        amount=m_share,
                        payment_date=service_payment.payment_date,
                    )

            main_filled += m_share
            sub_filled += s_share

        if not dry_run:
            main_tx.update_payment_status()
            sub_tx.update_payment_status()

        return len(service_payments)

    def handle(self, *args, **options):
        date_str = options.get('date')
        dry_run = options.get('dry_run', False)
        service_id = options.get('service_id')

        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d')
            target_date = timezone.make_aware(target_date)
        except ValueError:
            raise CommandError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")

        query = Q(
            created_at__gte=target_date,
            installation_units__isnull=False,
            status__in=[ServiceStatus.COMPLETED, ServiceStatus.IN_PROGRESS],
        )

        if service_id:
            query &= Q(id=service_id)

        services_to_fix = Service.objects.filter(query).distinct().order_by('id')
        count = services_to_fix.count()

        if count == 0:
            self.stdout.write(
                self.style.WARNING(
                    f"No matching installation services found from {date_str} onwards"
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"Found {count} services to process from {date_str} onwards")
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY-RUN mode (no changes will be saved)"))

        fixed_count = 0
        error_count = 0
        tx_type_fixed = 0
        ghost_cleaned = 0
        affected_client_ids = set(
            services_to_fix.filter(client__isnull=False).values_list('client_id', flat=True)
        )

        for idx, service in enumerate(services_to_fix, 1):
            try:
                client_name = getattr(service.client, 'full_name', None) or str(service.client) if service.client else 'Unknown'
                self.stdout.write(
                    f"\n[{idx}/{count}] Processing Service #{service.id} "
                    f"({client_name}) "
                    f"- Status: {service.status} - Created: {service.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
                )

                units = service.installation_units.all()
                if not units.exists():
                    self.stdout.write(self.style.WARNING("  ⊘ No aircon units found for this service"))
                    continue

                self.stdout.write(f"  ℹ Found {units.count()} installation unit(s)")

                # Update transaction types for any linked sales records in the date range.
                linked_txs = []
                if service.related_transaction_id:
                    linked_txs.append(service.related_transaction)
                if service.related_sub_transaction_id:
                    linked_txs.append(service.related_sub_transaction)

                for tx in linked_txs:
                    if tx and tx.transaction_type == TransactionType.SALE:
                        tx_type_fixed += 1
                        self.stdout.write(
                            self.style.WARNING(f"  ↳ Sales TX #{tx.id} marked as 'sale'; will update to 'service'")
                        )
                        if not dry_run:
                            tx.transaction_type = TransactionType.SERVICE
                            tx.save(update_fields=['transaction_type', 'updated_at'])

                # Ensure we have a main TX to work with.
                main_tx = service.related_transaction
                if not main_tx and service.payments.exists() and not dry_run:
                    # Fallback for services missing the main transaction link.
                    main_tx = ServicePaymentManager.recreate_sales_transaction(service)

                if not main_tx:
                    self.stdout.write(self.style.WARNING("  ⊘ No linked main sales transaction to update"))
                    continue

                # Ensure there is a sub transaction so the installation split exists in full.
                sub_tx, created_sub_tx = self._ensure_sub_transaction(service, main_tx, dry_run)

                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⊲ [DRY-RUN] Would rebuild installation sales split "
                            f"(Main: #{main_tx.id if main_tx else 'N/A'}, "
                            f"Sub: #{service.related_sub_transaction.id if service.related_sub_transaction else 'N/A'}, "
                            f"Payments: {service.payments.count()})"
                        )
                    )
                else:
                    # Rebuild the line items in place from the current service state.
                    ServicePaymentManager.sync_sales_items(service)
                    if sub_tx:
                        ServicePaymentManager.sync_sub_sales_items(service)

                    if created_sub_tx:
                        self.stdout.write(self.style.SUCCESS(f"  ✓ Created linked sub TX #{sub_tx.id}"))

                    # Rebalance mirrored payments sub-first, then main.
                    if sub_tx and service.payments.exists():
                        payment_rows = self._rebalance_service_payments(service, main_tx, sub_tx, dry_run=False)
                        self.stdout.write(
                            self.style.SUCCESS(f"  ✓ Rebuilt {payment_rows} payment mirror(s) across main/sub")
                        )

                    main_tx.update_payment_status()
                    if sub_tx:
                        sub_tx.update_payment_status()

                fixed_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Error processing Service #{service.id}: {str(e)}"))
                error_count += 1

        self.stdout.write("\n" + "=" * 70)

        # Cleanup orphan ghost service transactions in the same cutoff range.
        linked_main_ids = set(
            Service.objects.filter(related_transaction__isnull=False).values_list('related_transaction_id', flat=True)
        )
        linked_sub_ids = set(
            Service.objects.filter(related_sub_transaction__isnull=False).values_list('related_sub_transaction_id', flat=True)
        )
        linked_ids = linked_main_ids | linked_sub_ids

        ghost_candidates = SalesTransaction.objects.filter(
            transaction_type__in=[TransactionType.SERVICE, TransactionType.SALE],
            created_at__gte=target_date,
            payment_status='unpaid',
            voided=False,
            client_id__in=affected_client_ids,
        ).exclude(id__in=linked_ids)

        for tx in ghost_candidates:
            if tx.items.exists() or tx.payments.exists():
                continue
            ghost_cleaned += 1
            if not dry_run:
                tx.delete()

        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY-RUN SUMMARY]"))
        self.stdout.write(self.style.SUCCESS(f"Successfully processed: {fixed_count}/{count} services"))
        if tx_type_fixed > 0:
            self.stdout.write(self.style.SUCCESS(f"Updated {tx_type_fixed} linked sales transaction type(s) to 'service'."))
        if ghost_cleaned > 0:
            self.stdout.write(self.style.SUCCESS(f"Cleaned {ghost_cleaned} orphan zero-value service transaction(s)."))
        if error_count > 0:
            self.stdout.write(self.style.WARNING(f"Errors encountered: {error_count}/{count} services"))

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\nTo apply these changes, run without --dry-run:\n"
                    f"  python manage.py fix_installation_unit_revenue_split --date {date_str}"
                )
            )
