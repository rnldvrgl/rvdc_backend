"""
Management command to recalculate revenue for all services.
Use this after fixing revenue calculation logic to update existing services.
"""
from django.core.management.base import BaseCommand

from services.business_logic import RevenueCalculator
from services.models import Service


class Command(BaseCommand):
    help = 'Recalculate revenue for all services'

    def add_arguments(self, parser):
        parser.add_argument(
            '--service-id',
            type=int,
            help='Recalculate revenue for a specific service ID only',
        )

    def handle(self, *args, **options):
        service_id = options.get('service_id')

        if service_id:
            try:
                service = Service.objects.get(id=service_id)
                result = RevenueCalculator.calculate_service_revenue(service, save=True)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully recalculated revenue for Service #{service_id}\n'
                        f'Main Stall: {result["main_revenue"]}\n'
                        f'Sub Stall: {result["sub_revenue"]}\n'
                        f'Total: {result["total_revenue"]}'
                    )
                )
            except Service.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Service #{service_id} not found')
                )
        else:
            services = Service.objects.all()
            total = services.count()
            updated = 0

            self.stdout.write(f'Recalculating revenue for {total} services...')

            for service in services:
                try:
                    RevenueCalculator.calculate_service_revenue(service, save=True)
                    updated += 1
                    if updated % 100 == 0:
                        self.stdout.write(f'Processed {updated}/{total} services...')
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Failed to recalculate Service #{service.id}: {str(e)}'
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully recalculated revenue for {updated}/{total} services'
                )
            )
