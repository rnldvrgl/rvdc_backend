"""
Management command to transform all client names to uppercase.
This is useful for standardizing client name formatting across the database.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from clients.models import Client


class Command(BaseCommand):
    help = 'Transform all client names to uppercase'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without saving to database'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Get all clients (including soft-deleted ones)
        clients = Client.all_objects.all()
        total_clients = clients.count()
        
        if total_clients == 0:
            self.stdout.write(self.style.WARNING('No clients found in database'))
            return
        
        self.stdout.write(f'Found {total_clients} clients')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n=== DRY RUN MODE - No changes will be saved ===\n'))
        
        updated_count = 0
        unchanged_count = 0
        
        with transaction.atomic():
            for client in clients:
                original_name = client.full_name
                uppercase_name = original_name.upper()
                
                if original_name != uppercase_name:
                    if dry_run:
                        self.stdout.write(
                            f'  Would update: "{original_name}" → "{uppercase_name}"'
                        )
                    else:
                        client.full_name = uppercase_name
                        client.save(update_fields=['full_name'])
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  Updated: "{original_name}" → "{uppercase_name}"'
                            )
                        )
                    updated_count += 1
                else:
                    unchanged_count += 1
            
            if dry_run:
                # Rollback transaction in dry-run mode
                transaction.set_rollback(True)
        
        # Summary
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN SUMMARY:'))
            self.stdout.write(f'  Would update: {updated_count} clients')
        else:
            self.stdout.write(self.style.SUCCESS('TRANSFORMATION COMPLETE:'))
            self.stdout.write(self.style.SUCCESS(f'  Updated: {updated_count} clients'))
        
        self.stdout.write(f'  Unchanged: {unchanged_count} clients')
        self.stdout.write(f'  Total: {total_clients} clients')
        self.stdout.write('='*60)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\nRun without --dry-run to apply changes to database'
                )
            )
