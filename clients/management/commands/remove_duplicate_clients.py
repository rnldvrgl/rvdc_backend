from django.core.management.base import BaseCommand
from django.db.models import Count
from clients.models import Client


class Command(BaseCommand):
    help = 'Remove duplicate clients with the same contact number, keeping the oldest one'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write(self.style.WARNING('\n🔍 Finding duplicate contact numbers...\n'))

        # Find contact numbers that appear more than once
        duplicates = (
            Client.all_objects
            .values('contact_number')
            .annotate(count=Count('id'))
            .filter(count__gt=1, contact_number__isnull=False)
            .exclude(contact_number='')
        )

        if not duplicates.exists():
            self.stdout.write(self.style.SUCCESS('✅ No duplicate contact numbers found!'))
            return

        total_duplicates = duplicates.count()
        total_to_delete = 0

        self.stdout.write(f'Found {total_duplicates} contact numbers with duplicates:\n')

        for dup in duplicates:
            contact_number = dup['contact_number']
            count = dup['count']

            # Get all clients with this contact number, ordered by created_at (oldest first)
            clients_with_number = Client.all_objects.filter(
                contact_number=contact_number
            ).order_by('created_at')

            # Keep the first (oldest), delete the rest
            keep = clients_with_number.first()
            to_delete = clients_with_number.exclude(id=keep.id)

            self.stdout.write(f'\n📞 Contact Number: {contact_number} ({count} clients)')
            self.stdout.write(f'   ✅ KEEP: {keep.full_name} (ID: {keep.id}, Created: {keep.created_at})')

            for client in to_delete:
                total_to_delete += 1
                self.stdout.write(
                    f'   ❌ DELETE: {client.full_name} (ID: {client.id}, Created: {client.created_at})'
                )

        self.stdout.write(f'\n📊 Summary:')
        self.stdout.write(f'   • {total_duplicates} contact numbers have duplicates')
        self.stdout.write(f'   • {total_to_delete} clients will be deleted')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  DRY RUN - No changes made'))
            self.stdout.write('Run without --dry-run to actually delete duplicates')
            return

        # Confirm deletion
        self.stdout.write(self.style.WARNING('\n⚠️  This will permanently delete duplicate clients!'))
        confirm = input('Type "yes" to proceed: ')

        if confirm.lower() != 'yes':
            self.stdout.write(self.style.ERROR('\n❌ Aborted'))
            return

        # Delete duplicates
        deleted_count = 0
        for dup in duplicates:
            contact_number = dup['contact_number']
            clients_with_number = Client.all_objects.filter(
                contact_number=contact_number
            ).order_by('created_at')

            keep = clients_with_number.first()
            to_delete = clients_with_number.exclude(id=keep.id)

            count = to_delete.count()
            to_delete.delete()
            deleted_count += count

        self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully deleted {deleted_count} duplicate clients!'))
        self.stdout.write(self.style.SUCCESS('✅ Each contact number now appears only once'))
