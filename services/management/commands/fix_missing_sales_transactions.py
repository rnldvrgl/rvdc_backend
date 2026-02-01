"""
Management command to fix services with payments but no sales transaction.
"""
from django.core.management.base import BaseCommand
from services.models import Service
from services.business_logic import ServicePaymentManager


class Command(BaseCommand):
    help = "Recreate sales transactions for services with payments but no transaction"

    def handle(self, *args, **options):
        # Find services with payments but no valid transaction
        services_to_fix = []
        
        for service in Service.objects.all():
            if service.payments.exists():
                # Check if related_transaction exists and is valid
                if not service.related_transaction:
                    services_to_fix.append(service)
                else:
                    try:
                        # Try to access the transaction
                        service.related_transaction.id
                    except:
                        # Transaction doesn't exist
                        services_to_fix.append(service)
        
        if not services_to_fix:
            self.stdout.write(
                self.style.SUCCESS("No services need fixing. All services with payments have valid sales transactions.")
            )
            return
        
        self.stdout.write(f"Found {len(services_to_fix)} services with missing sales transactions.")
        
        for service in services_to_fix:
            self.stdout.write(f"Fixing service #{service.id}...")
            transaction = ServicePaymentManager.recreate_sales_transaction(service)
            if transaction:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Created sales transaction #{transaction.id} for service #{service.id}"
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(f"\nSuccessfully fixed {len(services_to_fix)} services!")
        )
