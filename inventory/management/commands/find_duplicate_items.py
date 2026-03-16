"""
Management command to find and report possible duplicate inventory items.

Usage:
    python manage.py find_duplicate_items           # Report only
    python manage.py find_duplicate_items --normalize  # Normalize all names to Title Case
"""

import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from inventory.models import Item, ProductCategory, normalize_name


class Command(BaseCommand):
    help = "Find possible duplicate inventory items and optionally normalize names to Title Case."

    def add_arguments(self, parser):
        parser.add_argument(
            "--normalize",
            action="store_true",
            help="Normalize all item & category names to Title Case (apply changes).",
        )

    def handle(self, *args, **options):
        do_normalize = options["normalize"]

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Inventory Duplicate Report ===\n"))

        # ---- Step 1: Normalize names if requested ----
        if do_normalize:
            self._normalize_categories()
            self._normalize_items()

        # ---- Step 2: Find exact duplicates (same normalized name) ----
        self._find_exact_duplicates()

        # ---- Step 3: Find fuzzy / token-overlap duplicates ----
        self._find_fuzzy_duplicates()

        self.stdout.write(self.style.SUCCESS("\n=== Report Complete ===\n"))

    # ------------------------------------------------------------------
    # Normalize
    # ------------------------------------------------------------------
    def _normalize_categories(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Normalizing Category Names ---"))
        updated = 0
        for cat in ProductCategory.all_objects.all():
            new_name = normalize_name(cat.name)
            if new_name != cat.name:
                self.stdout.write(f"  Category #{cat.pk}: '{cat.name}' -> '{new_name}'")
                cat.name = new_name
                cat.save(update_fields=["name"])
                updated += 1
        self.stdout.write(f"  Categories updated: {updated}\n")

    def _normalize_items(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Normalizing Item Names ---"))
        updated = 0
        for item in Item.all_objects.all():
            new_name = normalize_name(item.name)
            if new_name != item.name:
                self.stdout.write(f"  Item #{item.pk}: '{item.name}' -> '{new_name}'")
                item.name = new_name
                # Skip price history tracking for name-only normalization
                item.save(update_fields=["name"])
                updated += 1
        self.stdout.write(f"  Items updated: {updated}\n")

    # ------------------------------------------------------------------
    # Exact duplicates (same name after lowercasing + collapsing spaces)
    # ------------------------------------------------------------------
    def _find_exact_duplicates(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Exact Duplicates (same normalized name) ---"))
        items = Item.objects.filter(is_deleted=False).select_related("category")

        groups = defaultdict(list)
        for item in items:
            key = re.sub(r"\s+", " ", item.name.strip().lower())
            groups[key].append(item)

        found = 0
        for key, group in sorted(groups.items()):
            if len(group) > 1:
                found += 1
                self.stdout.write(self.style.WARNING(f"\n  Duplicate group: '{key}'"))
                for item in group:
                    cat_name = item.category.name if item.category else "No Category"
                    self.stdout.write(
                        f"    -> #{item.pk} | Name: '{item.name}' | SKU: {item.sku} "
                        f"| Category: {cat_name} | Retail: {item.retail_price}"
                    )

        if not found:
            self.stdout.write(self.style.SUCCESS("  No exact duplicates found."))
        else:
            self.stdout.write(self.style.WARNING(f"\n  Total duplicate groups: {found}"))

    # ------------------------------------------------------------------
    # Fuzzy duplicates (token overlap >= 60%)
    # ------------------------------------------------------------------
    def _find_fuzzy_duplicates(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Similar Items (word-overlap ≥ 60%) ---"))
        items = list(
            Item.objects.filter(is_deleted=False)
            .select_related("category")
            .order_by("name")
        )

        # Pre-compute token sets
        tokenized = []
        for item in items:
            tokens = set(re.sub(r"\s+", " ", item.name.strip().lower()).split())
            tokenized.append((item, tokens))

        reported_pairs = set()
        similar_groups = []

        for i, (item_a, tokens_a) in enumerate(tokenized):
            for j, (item_b, tokens_b) in enumerate(tokenized):
                if j <= i:
                    continue
                pair_key = (min(item_a.pk, item_b.pk), max(item_a.pk, item_b.pk))
                if pair_key in reported_pairs:
                    continue

                overlap = len(tokens_a & tokens_b)
                total = max(len(tokens_a | tokens_b), 1)
                ratio = overlap / total

                # Also check if one name is a substring of the other
                a_lower = item_a.name.lower()
                b_lower = item_b.name.lower()
                is_substring = a_lower in b_lower or b_lower in a_lower

                if ratio >= 0.6 or is_substring:
                    reported_pairs.add(pair_key)
                    similar_groups.append((item_a, item_b, ratio, is_substring))

        if not similar_groups:
            self.stdout.write(self.style.SUCCESS("  No similar items found."))
        else:
            for item_a, item_b, ratio, is_sub in similar_groups:
                match_info = f"overlap={ratio:.0%}"
                if is_sub:
                    match_info += " + substring"
                cat_a = item_a.category.name if item_a.category else "No Category"
                cat_b = item_b.category.name if item_b.category else "No Category"
                self.stdout.write(
                    self.style.WARNING(f"\n  Possible duplicate ({match_info}):")
                )
                self.stdout.write(
                    f"    A: #{item_a.pk} '{item_a.name}' | SKU: {item_a.sku} | Category: {cat_a}"
                )
                self.stdout.write(
                    f"    B: #{item_b.pk} '{item_b.name}' | SKU: {item_b.sku} | Category: {cat_b}"
                )

            self.stdout.write(
                self.style.WARNING(f"\n  Total similar pairs: {len(similar_groups)}")
            )
