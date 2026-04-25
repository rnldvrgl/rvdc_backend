"""
Rebuild service sales line-item descriptions where custom parts still show as
"Custom Item" instead of the entered custom_description.

Usage:
    python manage.py fix_custom_item_descriptions
    python manage.py fix_custom_item_descriptions --dry-run
    python manage.py fix_custom_item_descriptions --service-id 123
    python manage.py fix_custom_item_descriptions --date 2026-04-01
"""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from services.business_logic import ServicePaymentManager
from services.models import Service


class Command(BaseCommand):
    help = (
        "Rebuild service sales items for records still using generic "
        "'Custom Item' descriptions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without writing to the database",
        )
        parser.add_argument(
            "--service-id",
            type=int,
            help="Only process a specific service ID",
        )
        parser.add_argument(
            "--date",
            type=str,
            help="Only process services created on/after this date (YYYY-MM-DD)",
        )

    def _parse_date(self, date_str):
        if not date_str:
            return None
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
            return timezone.make_aware(target_date)
        except ValueError as exc:
            raise CommandError(f"Invalid date format: {date_str}. Use YYYY-MM-DD") from exc

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        service_id = options.get("service_id")
        target_date = self._parse_date(options.get("date"))

        # Include both legacy generic labels and blank custom-line descriptions.
        custom_desc_query = (
            Q(description="Custom Item") |
            Q(description="") |
            Q(description__isnull=True)
        )

        query = Q(
            related_transaction__items__item__isnull=True,
            related_transaction__items__transaction__voided=False,
        ) & custom_desc_query

        query |= Q(
            related_sub_transaction__items__item__isnull=True,
            related_sub_transaction__items__transaction__voided=False,
        ) & custom_desc_query

        if service_id:
            query &= Q(id=service_id)
        if target_date:
            query &= Q(created_at__gte=target_date)

        services = (
            Service.objects.filter(query)
            .select_related("related_transaction", "related_sub_transaction", "client")
            .prefetch_related(
                "appliances__items_used__item",
                "service_items__item",
                "installation_units__model__brand",
            )
            .distinct()
            .order_by("id")
        )

        total = services.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("No matching services found."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {total} service(s) to process."))
        if dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY-RUN mode (no changes will be saved)"))

        fixed = 0
        skipped = 0
        errors = 0

        for idx, service in enumerate(services, 1):
            try:
                client_name = (
                    getattr(service.client, "full_name", None)
                    or str(service.client)
                    if service.client
                    else "Unknown"
                )
                self.stdout.write(
                    f"\n[{idx}/{total}] Service #{service.id} ({client_name})"
                )

                main_tx = service.related_transaction
                sub_tx = service.related_sub_transaction

                main_has_generic = bool(
                    main_tx and main_tx.items.filter(item__isnull=True).filter(custom_desc_query).exists()
                )
                sub_has_generic = bool(
                    sub_tx and sub_tx.items.filter(item__isnull=True).filter(custom_desc_query).exists()
                )

                if not main_has_generic and not sub_has_generic:
                    skipped += 1
                    self.stdout.write("  ⊘ No generic custom labels remain, skipping")
                    continue

                self.stdout.write(
                    f"  ℹ Generic labels found (main={main_has_generic}, sub={sub_has_generic})"
                )

                if dry_run:
                    fixed += 1
                    self.stdout.write(
                        self.style.WARNING("  ⊲ [DRY-RUN] Would rebuild sales item descriptions")
                    )
                    continue

                with transaction.atomic():
                    if main_tx:
                        ServicePaymentManager.sync_sales_items(service)
                    if sub_tx:
                        ServicePaymentManager.sync_sub_sales_items(service)

                fixed += 1
                self.stdout.write(self.style.SUCCESS("  ✓ Rebuilt sales item descriptions"))

            except Exception as exc:
                errors += 1
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {exc}"))

        self.stdout.write("\n" + "=" * 70)
        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY-RUN SUMMARY]"))
        self.stdout.write(self.style.SUCCESS(f"Processed: {fixed}/{total}"))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped: {skipped}"))
        if errors:
            self.stdout.write(self.style.WARNING(f"Errors: {errors}"))

        if dry_run:
            cmd = "python manage.py fix_custom_item_descriptions"
            if target_date:
                cmd += f" --date {target_date.date()}"
            if service_id:
                cmd += f" --service-id {service_id}"
            self.stdout.write(self.style.WARNING(f"\nRun without --dry-run to apply:\n  {cmd}"))
