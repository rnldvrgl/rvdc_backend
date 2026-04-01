"""
Management command to fix completed services with zero total revenue
that are stuck with 'unpaid' payment status.

These services should be marked as 'paid' (or complementary) since
there's nothing to pay.

Usage:
    python manage.py fix_zero_balance_payment_status
    python manage.py fix_zero_balance_payment_status --dry-run
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from services.models import Service


class Command(BaseCommand):
    help = 'Fix completed services with zero total revenue stuck as unpaid'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved\n'))

        # Find completed services with zero/negative total revenue and unpaid status
        zero_balance_services = Service.objects.filter(
            status='completed',
            payment_status__in=['unpaid', 'pending'],
        ).select_related('client')

        fixed = 0
        skipped = 0

        for service in zero_balance_services:
            total_revenue = service.total_revenue or Decimal('0')

            if total_revenue <= 0:
                if dry_run:
                    self.stdout.write(
                        f"  [DRY RUN] Service #{service.id} "
                        f"(client: {service.client}) — "
                        f"revenue: {total_revenue}, "
                        f"status: {service.payment_status} → paid"
                    )
                else:
                    service.payment_status = 'paid'
                    update_fields = ['payment_status', 'updated_at']

                    # Also mark as complementary if not already
                    if not service.is_complementary:
                        service.is_complementary = True
                        update_fields.append('is_complementary')

                    service.save(update_fields=update_fields)
                    self.stdout.write(
                        f"  Fixed Service #{service.id} "
                        f"(client: {service.client}) → paid"
                    )
                fixed += 1
            else:
                skipped += 1

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'Would fix {fixed} services. '
                f'Skipped {skipped} (have revenue > 0, need actual payments).'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Fixed {fixed} services. '
                f'Skipped {skipped} (have revenue > 0).'
            ))
