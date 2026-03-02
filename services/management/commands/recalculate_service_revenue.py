"""
Management command to recalculate revenue for all services.
Useful after updating revenue calculation logic or fixing unit price integration.

Usage:
    python manage.py recalculate_service_revenue
    python manage.py recalculate_service_revenue --installations-only
    python manage.py recalculate_service_revenue --service-id 123
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from services.models import Service
from services.business_logic import RevenueCalculator


class Command(BaseCommand):
    help = 'Recalculate revenue for services'

    def add_arguments(self, parser):
        parser.add_argument(
            '--installations-only',
            action='store_true',
            help='Only recalculate revenue for installation services',
        )
        parser.add_argument(
            '--service-id',
            type=int,
            help='Recalculate revenue for a specific service',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving',
        )

    def handle(self, *args, **options):
        installations_only = options['installations_only']
        service_id = options['service_id']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        # Build query
        if service_id:
            services = Service.objects.filter(id=service_id)
            if not services.exists():
                self.stdout.write(self.style.ERROR(f'Service {service_id} not found'))
                return
        elif installations_only:
            services = Service.objects.filter(service_type='installation')
        else:
            services = Service.objects.all()

        services = services.select_related('client').prefetch_related(
            'appliances__items_used',
            'installation_units__model__brand'
        )

        total = services.count()
        self.stdout.write(f'Processing {total} services...\n')

        updated = 0
        unchanged = 0
        errors = 0

        for service in services:
            try:
                # Get old values
                old_main = service.main_stall_revenue
                old_sub = service.sub_stall_revenue
                old_total = service.total_revenue

                # Calculate new values
                result = RevenueCalculator.calculate_service_revenue(service, save=not dry_run)
                
                new_main = result['main_revenue']
                new_sub = result['sub_revenue']
                new_total = result['total_revenue']

                # Check if changed
                if old_main != new_main or old_sub != new_sub or old_total != new_total:
                    updated += 1
                    self.stdout.write(
                        f'✓ Service #{service.id} ({service.service_type}) - '
                        f'Main: {old_main} → {new_main}, '
                        f'Sub: {old_sub} → {new_sub}, '
                        f'Total: {old_total} → {new_total}'
                    )
                    
                    # Show installation units if it's an installation service
                    if service.service_type == 'installation' and service.installation_units.exists():
                        unit_count = service.installation_units.count()
                        self.stdout.write(f'  └─ {unit_count} installation unit(s) included')
                else:
                    unchanged += 1
                    if options['verbosity'] > 1:
                        self.stdout.write(
                            f'- Service #{service.id} unchanged (Total: {new_total})'
                        )

            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f'✗ Service #{service.id}: {str(e)}')
                )

        # Summary
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(f'Total processed: {total}')
        self.stdout.write(self.style.SUCCESS(f'Updated: {updated}'))
        self.stdout.write(f'Unchanged: {unchanged}')
        if errors:
            self.stdout.write(self.style.ERROR(f'Errors: {errors}'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No changes were saved'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ Revenue recalculation complete'))
