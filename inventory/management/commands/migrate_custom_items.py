"""
migrate_custom_items
====================
One-time migration command that:

1. Converts every active CustomItemTemplate into an untracked Item
   (is_tracked=False).  If an item with the same name already exists
   it is left alone (not duplicated).

2. Auto-links all custom/free-text rows in:
     - sales.SalesItem            (item=null, description=<name>)
     - services.ApplianceItemUsed (item=null, custom_description=<name>)
     - services.ServiceItemUsed   (item=null, custom_description=<name>)
   to their matching Item using a case-insensitive exact-name match.

3. Prints a summary report of what was linked and what still needs manual
   review via the admin UI (/admin/custom-item-migration/).

Usage
-----
    python manage.py migrate_custom_items          # dry run (default)
    python manage.py migrate_custom_items --apply  # actually write to DB
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Migrate CustomItemTemplate entries to untracked Items and auto-link historical custom rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write changes to the database. Omit for a dry-run preview.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        mode = "APPLY" if apply else "DRY RUN"
        self.stdout.write(self.style.WARNING(f"\n=== migrate_custom_items [{mode}] ===\n"))

        with transaction.atomic():
            self._convert_templates(apply)
            linked, unmatched = self._auto_link(apply)

            if apply:
                self.stdout.write(self.style.SUCCESS(f"\n✓ Done. Linked {linked} rows."))
            else:
                self.stdout.write(self.style.NOTICE(f"\n[DRY RUN] Would link {linked} rows."))
                self.stdout.write(
                    "Run with --apply to commit changes.\n"
                )

            if unmatched:
                self.stdout.write(
                    self.style.WARNING(
                        f"\n{len(unmatched)} unique descriptions still unmatched — "
                        "review them in the admin UI at /admin/custom-item-migration/\n"
                    )
                )
                self.stdout.write(
                    f"  {'Description':<40} {'Count':>6}  {'Avg Price':>10}\n"
                    + "  " + "-" * 62
                )
                for desc, count, avg in sorted(unmatched, key=lambda x: -x[1])[:50]:
                    avg_str = f"₱{avg:.2f}" if avg else "N/A"
                    self.stdout.write(f"  {desc:<40} {count:>6}  {avg_str:>10}")
                if len(unmatched) > 50:
                    self.stdout.write(f"  ... and {len(unmatched) - 50} more.")

            if not apply:
                # Roll back all DB changes in dry-run mode
                transaction.set_rollback(True)

    # ------------------------------------------------------------------
    def _convert_templates(self, apply: bool):
        from inventory.models import CustomItemTemplate, Item

        templates = list(CustomItemTemplate.objects.filter(is_active=True))
        self.stdout.write(f"CustomItemTemplates to convert: {len(templates)}")

        created = 0
        skipped = 0
        for tmpl in templates:
            existing = Item.all_objects.filter(
                name__iexact=tmpl.name, is_deleted=False
            ).first()
            if existing:
                skipped += 1
                self.stdout.write(
                    f"  SKIP  '{tmpl.name}' — already exists as Item #{existing.pk}"
                )
                continue

            if apply:
                item = Item(
                    name=tmpl.name,
                    retail_price=tmpl.default_price,
                    description=tmpl.description or "",
                    is_tracked=False,
                )
                item.save()
                self.stdout.write(
                    self.style.SUCCESS(f"  CREATED  Item #{item.pk} '{item.name}' (untracked)")
                )
            else:
                self.stdout.write(
                    f"  [would create] '{tmpl.name}' @ ₱{tmpl.default_price} (untracked)"
                )
            created += 1

        self.stdout.write(
            f"  → created: {created}, skipped (already exists): {skipped}\n"
        )

    # ------------------------------------------------------------------
    def _auto_link(self, apply: bool) -> tuple[int, list]:
        from inventory.models import Item
        from sales.models import SalesItem
        from services.models import ApplianceItemUsed, ServiceItemUsed

        # Build a lookup: normalised name → Item
        item_map: dict[str, object] = {}
        for item in Item.objects.filter(is_deleted=False):
            item_map[item.name.strip().lower()] = item

        total_linked = 0
        unmatched_map: dict[str, list] = {}  # desc_lower → [count, avg_price]

        def _link_batch(qs, desc_field: str, price_field: str, label: str):
            nonlocal total_linked
            rows = list(qs.filter(item__isnull=True).exclude(**{desc_field: ""}))
            linked = 0
            for row in rows:
                desc = (getattr(row, desc_field) or "").strip()
                key = desc.lower()
                match = item_map.get(key)
                if match:
                    if apply:
                        type(row).objects.filter(pk=row.pk).update(item=match)
                    linked += 1
                else:
                    price = getattr(row, price_field, None)
                    if key not in unmatched_map:
                        unmatched_map[key] = [desc, 0, 0.0, 0]
                    unmatched_map[key][1] += 1
                    if price is not None:
                        unmatched_map[key][2] += float(price)
                        unmatched_map[key][3] += 1

            verb = "Linked" if apply else "Would link"
            self.stdout.write(f"  {label}: {verb} {linked} / {len(rows)} rows")
            total_linked += linked

        self.stdout.write("Auto-linking by exact name match:")
        _link_batch(SalesItem.objects, "description", "final_price_per_unit", "SalesItem")
        _link_batch(ApplianceItemUsed.objects, "custom_description", "custom_price", "ApplianceItemUsed")
        _link_batch(ServiceItemUsed.objects, "custom_description", "custom_price", "ServiceItemUsed")

        # Build unmatched report
        unmatched = []
        for key, (desc, count, price_sum, price_count) in unmatched_map.items():
            avg = price_sum / price_count if price_count else None
            unmatched.append((desc, count, avg))

        return total_linked, unmatched
