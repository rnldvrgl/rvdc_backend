"""
Management command to delete old notifications.
Should be run via cron/scheduler daily or weekly.

Usage:
    python manage.py delete_old_notifications              # Delete read notifications older than 7 days
    python manage.py delete_old_notifications --days 14    # Custom retention period
    python manage.py delete_old_notifications --all        # Delete ALL notifications older than threshold (not just read)
    python manage.py delete_old_notifications --dry-run    # Preview without deleting
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.models import Notification


class Command(BaseCommand):
    help = "Delete old notifications (default: read notifications older than 7 days)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Delete notifications older than this many days (default: 7)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Delete ALL old notifications, not just read ones",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        days = options["days"]
        delete_all = options["all"]
        dry_run = options["dry_run"]

        cutoff_date = timezone.now() - timedelta(days=days)

        self.stdout.write(
            self.style.WARNING(
                f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')} "
                f"({days} days ago)"
            )
        )

        # Build queryset
        qs = Notification.objects.filter(created_at__lt=cutoff_date)

        if not delete_all:
            qs = qs.filter(is_read=True)
            scope = "read"
        else:
            scope = "all"

        total_count = qs.count()

        if total_count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No {scope} notifications older than {days} days found."
                )
            )
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would delete {total_count} {scope} notification(s) "
                    f"older than {days} days."
                )
            )
            return

        count, _ = qs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {count} {scope} notification(s) older than {days} days."
            )
        )
