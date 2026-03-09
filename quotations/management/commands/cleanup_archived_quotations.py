"""
Delete archived quotations older than 14 days.

Runs via cron daily. Only removes quotations where
is_deleted=True AND deleted_at is older than 14 days.

Usage:
    python manage.py cleanup_archived_quotations
    python manage.py cleanup_archived_quotations --days 7
    python manage.py cleanup_archived_quotations --dry-run
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from quotations.models import Quotation


class Command(BaseCommand):
    help = "Permanently delete archived quotations older than N days (default: 14)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=14,
            help="Delete archived quotations older than this many days (default: 14)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without making changes",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=days)

        qs = Quotation.objects.filter(is_deleted=True, deleted_at__lte=cutoff)
        count = qs.count()

        if count == 0:
            self.stdout.write("No archived quotations older than %d days." % days)
            return

        if dry_run:
            self.stdout.write(
                "DRY RUN: Would delete %d archived quotation(s) older than %d days."
                % (count, days)
            )
            for q in qs[:20]:
                self.stdout.write(
                    "  - #%d %s (archived %s)"
                    % (q.pk, q.client_name or "No Client", q.deleted_at)
                )
            return

        deleted_count, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                "Permanently deleted %d archived quotation(s) older than %d days."
                % (deleted_count, days)
            )
        )
