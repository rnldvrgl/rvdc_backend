"""
migrate_custom_items
====================
One-time migration command that:

1. Creates pre-defined untracked Items that don't yet exist in inventory
   (e.g. "Motor Rewind") so they can be referenced going forward.

2. Converts every active CustomItemTemplate into an untracked Item
   (is_tracked=False).  If an item with the same name already exists
   it is left alone (not duplicated).

3. Auto-links all custom/free-text rows in:
     - sales.SalesItem            (item=null, description=<name>)
     - services.ApplianceItemUsed (item=null, custom_description=<name>)
     - services.ServiceItemUsed   (item=null, custom_description=<name>)
   to their matching Item using:
     a) explicit alias mappings (for known variants like copper pipe)
     b) case-insensitive exact-name match

4. Prints a summary report of what was linked and what still needs manual
   review.

Usage
-----
    python manage.py migrate_custom_items          # dry run (default)
    python manage.py migrate_custom_items --apply  # actually write to DB
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

# Items to create if they don't exist (untracked catalogue entries)
ITEMS_TO_CREATE = [
    {
        "name": "Motor Rewind",
        "category_name": "motor",
        "retail_price": Decimal("350.00"),
        "wholesale_price": Decimal("350.00"),
        "technician_price": Decimal("350.00"),
        "cost_price": Decimal("0.00"),
        "unit_of_measure": "pcs",
        "is_tracked": False,
    },
    {
        "name": "ELECTRICAL TAPE",
        "category_name": "tape",
        "retail_price": Decimal("45.00"),
        "wholesale_price": Decimal("45.00"),
        "technician_price": Decimal("45.00"),
        "cost_price": Decimal("0.00"),
        "unit_of_measure": "pcs",
        "is_tracked": False,
    },
    {
        "name": "PVC PIPE BLUE",
        "category_name": "others",
        "retail_price": Decimal("125.00"),
        "wholesale_price": Decimal("125.00"),
        "technician_price": Decimal("125.00"),
        "cost_price": Decimal("0.00"),
        "unit_of_measure": "pcs",
        "is_tracked": False,
    },
    {
        "name": "MICROWAVE SWITCH",
        "category_name": "switch",
        "retail_price": Decimal("130.00"),
        "wholesale_price": Decimal("130.00"),
        "technician_price": Decimal("130.00"),
        "cost_price": Decimal("0.00"),
        "unit_of_measure": "pcs",
        "is_tracked": False,
    },
    {
        "name": "GLASS TYPE FUSE 5AMP",
        "category_name": "fuse",
        "retail_price": Decimal("50.00"),
        "wholesale_price": Decimal("50.00"),
        "technician_price": Decimal("50.00"),
        "cost_price": Decimal("0.00"),
        "unit_of_measure": "pcs",
        "is_tracked": False,
    },
    {
        "name": "CONDENSER REFRIGERATOR",
        "category_name": "others",
        "retail_price": Decimal("900.00"),
        "wholesale_price": Decimal("900.00"),
        "technician_price": Decimal("900.00"),
        "cost_price": Decimal("0.00"),
        "unit_of_measure": "pcs",
        "is_tracked": False,
    },
    {
        "name": "FLARE UNION 1/4",
        "category_name": "nut",
        "retail_price": Decimal("80.00"),
        "wholesale_price": Decimal("80.00"),
        "technician_price": Decimal("80.00"),
        "cost_price": Decimal("0.00"),
        "unit_of_measure": "pcs",
        "is_tracked": False,
    },
    {
        "name": "Empty Tank",
        "category_name": "tank",
        "retail_price": Decimal("150.00"),
        "wholesale_price": Decimal("150.00"),
        "technician_price": Decimal("150.00"),
        "cost_price": Decimal("0.00"),
        "unit_of_measure": "pcs",
        "is_tracked": False,
    },
    {
        "name": "Royal Cord 14/3 (Meter)",
        "category_name": "cord",
        "retail_price": Decimal("480.00"),
        "wholesale_price": Decimal("480.00"),
        "technician_price": Decimal("480.00"),
        "cost_price": Decimal("0.00"),
        "unit_of_measure": "meter",
        "is_tracked": False,
    },
]

# Alias mappings: custom description (lowercase) → inventory item name
# Handles known name variants that won't match by exact name.
ALIAS_MAP = {
    # Motor Rewind
    "motor rewind": "Motor Rewind",
    "custom item": "Motor Rewind",
    # Copper Pipe 1/4 variants
    "1/4 copper pipe (feet)": "COPPER PIPE 1/4X.028",
    "copper ins. 1/4": "COPPER PIPE 1/4X.028",
    "copper pipe 1/4": "COPPER PIPE 1/4X.028",
    "1/4 copper tube": "COPPER PIPE 1/4X.028",
    # Copper Pipe 3/8 variants
    "3/8 copper pipe (feet)": "COPPER PIPE 3/8X.028",
    "copper ins. 3/8": "COPPER PIPE 3/8X.028",
    "copper pipe 3/8": "COPPER PIPE 3/8X.028",
    "3/8 copper tube": "COPPER PIPE 3/8X.028",
    # Copper Pipe 5/8
    "5/8 copper pipe (feet)": "COPPER PIPE 5/8X.028",
    # Copper Pipe 1/2
    "copper pipe 1/2": "COPPER PIPE 1/2X.028",
    # Wash Motor
    "wash motor": "MOTOR WASH NATIONAL 10MM",
    # Refrigerants
    "refrigerant r-32": "REFRIGERANT R-32 (PER KILO)",
    "refrigerant r-32 (per kilo)": "REFRIGERANT R-32 (PER KILO)",
    "freon 134a": "REFRIGERANT 134A (PER KILO)",
    "refrigerant 134a (per kilo)": "REFRIGERANT 134A (PER KILO)",
    "refrigerant 410a": "REFRIGERANT 410A (PER KILO)",
    "refrigerant 410a (kilo)": "REFRIGERANT 410A (PER KILO)",
    # Hose / Ferrule
    "hose": "SILICON HOSE",
    "ferulle 1/2": 'FERULLE 1/2"',
    # Insulation
    "insulation tube 5/8": "RUBBER INSULATION 5/8 X 1/2",
    "insulation tube 1/4": "RUBBER INSULATION 1/4 X 1/2",
    "insulation tube 1/2": "RUBBER INSULATION 1/2 X 1/2",
    "7/8 x 3/8 insulation tube": "RUBBER INSULATION 7/8 X 3/4",
    # Wire / Electrical
    "wire": "LEAD WIRE CUT",
    "elbow": "ELBOW 1/4 90DEG",
    "electrical tape": "ELECTRICAL TAPE",
    "pvc pipe blue": "PVC PIPE BLUE",
    # Blades
    "window type blade 5 petals": "WINDOW TYPE BLADE PETALS",
    'blade bagyo 18"': 'BLADE BANANA 18" HALFMOON',
    # Gear Cases
    "gear case": "GEARCASE 10T CAMEL",
    "gear case union 11-t": "GEARCASE 11T UNION",
    # Switches / Fuses / Capacitors
    "microwave switch": "MICROWAVE SWITCH",
    "knob": "KNOB WASHING SHARP",
    "fuse box type electric fan": "FUSE 2AMP BOX TYPE",
    "capacitor 2uf electric fan": "CAPACITOR 2.0UF ELECTRIC FAN",
    "magnetic switch rice cooker": "MAGNETIC POINT RICE COOKER",
    "glass type fuse 5amp": "GLASS TYPE FUSE 5AMP",
    "thermal fuse 10amp": "FUSE 10AMP.RICE COOKER METAL",
    "thermal fuse 2amp": "FUSE 2AMP BOX TYPE",
    # Oil
    "oil": "JUKI OIL",
    # Condenser / Nut / Union
    "condenser refrigerator": "CONDENSER REFRIGERATOR",
    "flare union 1/4": "FLARE UNION 1/4",
    # Empty Tank
    "empty tank": "Empty Tank",
    # Royal Cord
    "royal cored 14/3": "Royal Cord 14/3 (Meter)",
}

# Descriptions that need special handling (splits, quantity/price overrides).
# Handled by _fix_special_items() BEFORE _auto_link().
# Keys are lowercase descriptions.
SPECIAL_DESCRIPTIONS = {
    # Split: 1 SET copper ins → 10ft of 1/4 + 10ft of 3/8
    "1set copper ins. 3/8 1/4": {
        "action": "split",
        "items": [
            {"target": "COPPER PIPE 1/4X.028", "quantity": Decimal("10"), "price": Decimal("55.00")},
            {"target": "COPPER PIPE 3/8X.028", "quantity": Decimal("10"), "price": Decimal("65.00")},
        ],
    },
    # Split: copper tube set → 10ft of 1/4 + 10ft of 3/8
    "copper tube set 1/4 and 3/8": {
        "action": "split",
        "items": [
            {"target": "COPPER PIPE 1/4X.028", "quantity": Decimal("10"), "price": Decimal("55.00")},
            {"target": "COPPER PIPE 3/8X.028", "quantity": Decimal("10"), "price": Decimal("65.00")},
        ],
    },
    # "copper pipe" at 550 → 10ft of COPPER PIPE 1/4X.028 at 55/ft
    "copper pipe": {
        "action": "link_override",
        "target": "COPPER PIPE 1/4X.028",
        "quantity": Decimal("10"),
        "price": Decimal("55.00"),
    },
    # Half kilo of R-32
    "freon r-32 (half)": {
        "action": "link_override",
        "target": "REFRIGERANT R-32 (PER KILO)",
        "quantity": Decimal("0.5"),
    },
    # Half kilo of R-32
    "refrigerant r32(1/2 kg)": {
        "action": "link_override",
        "target": "REFRIGERANT R-32 (PER KILO)",
        "quantity": Decimal("0.5"),
    },
}


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
            self._create_predefined_items(apply)
            self._convert_templates(apply)
            self._link_known_empty_items(apply)
            self._fix_special_items(apply)
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
    def _create_predefined_items(self, apply: bool):
        from inventory.models import Item, ProductCategory

        self.stdout.write("Creating predefined untracked items:")
        created = 0
        skipped = 0

        for spec in ITEMS_TO_CREATE:
            existing = Item.all_objects.filter(
                name__iexact=spec["name"], is_deleted=False
            ).first()
            if existing:
                skipped += 1
                self.stdout.write(
                    f"  SKIP  '{spec['name']}' — already exists as Item #{existing.pk}"
                )
                continue

            category = None
            if spec.get("category_name"):
                category = ProductCategory.objects.filter(
                    name__iexact=spec["category_name"]
                ).first()

            if apply:
                item = Item(
                    name=spec["name"],
                    retail_price=spec["retail_price"],
                    wholesale_price=spec.get("wholesale_price", Decimal("0")),
                    technician_price=spec.get("technician_price", Decimal("0")),
                    cost_price=spec.get("cost_price", Decimal("0")),
                    unit_of_measure=spec.get("unit_of_measure", "pcs"),
                    is_tracked=spec.get("is_tracked", False),
                    category=category,
                )
                item.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  CREATED  Item #{item.pk} '{item.name}' "
                        f"(untracked, category={category})"
                    )
                )
            else:
                self.stdout.write(
                    f"  [would create] '{spec['name']}' @ ₱{spec['retail_price']} "
                    f"(untracked, category={spec.get('category_name', 'none')})"
                )
            created += 1

        self.stdout.write(
            f"  → created: {created}, skipped (already exists): {skipped}\n"
        )

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
    def _link_known_empty_items(self, apply: bool):
        """
        Handle the 9 known items with empty custom_description in production.
        These are service/appliance records where the description was left blank
        but we know from the user what they should be.
        """
        from inventory.models import Item
        from services.models import ApplianceItemUsed, ServiceItemUsed

        KNOWN_SERVICE_ITEMS = {
            33: "COPPER PIPE 1/4X.028",
            34: "COPPER PIPE 3/8X.028",
            38: "COPPER PIPE 1/4X.028",
            48: "Motor Rewind",
            52: "Motor Rewind",
        }
        KNOWN_APPLIANCE_ITEMS = {
            133: "Motor Rewind",
            142: "Motor Rewind",
            160: "Motor Rewind",
            171: "Motor Rewind",
        }

        item_cache: dict[str, object] = {}
        for name in set(list(KNOWN_SERVICE_ITEMS.values()) + list(KNOWN_APPLIANCE_ITEMS.values())):
            item = Item.objects.filter(name__iexact=name, is_deleted=False).first()
            if item:
                item_cache[name] = item
            else:
                self.stdout.write(
                    self.style.WARNING(f"  WARNING: Item '{name}' not found — cannot link")
                )

        self.stdout.write("Linking known empty-description items:")
        linked = 0

        for pk, target_name in KNOWN_SERVICE_ITEMS.items():
            target = item_cache.get(target_name)
            if not target:
                continue
            row = ServiceItemUsed.objects.filter(pk=pk, item__isnull=True).first()
            if not row:
                self.stdout.write(f"  SKIP  ServiceItemUsed #{pk} — already linked or not found")
                continue
            if apply:
                ServiceItemUsed.objects.filter(pk=pk).update(
                    item=target,
                    custom_description=target_name,
                )
            linked += 1
            verb = "Linked" if apply else "Would link"
            self.stdout.write(f"  {verb} ServiceItemUsed #{pk} → '{target_name}'")

        for pk, target_name in KNOWN_APPLIANCE_ITEMS.items():
            target = item_cache.get(target_name)
            if not target:
                continue
            row = ApplianceItemUsed.objects.filter(pk=pk, item__isnull=True).first()
            if not row:
                self.stdout.write(f"  SKIP  ApplianceItemUsed #{pk} — already linked or not found")
                continue
            if apply:
                ApplianceItemUsed.objects.filter(pk=pk).update(
                    item=target,
                    custom_description=target_name,
                )
            linked += 1
            verb = "Linked" if apply else "Would link"
            self.stdout.write(f"  {verb} ApplianceItemUsed #{pk} → '{target_name}'")

        self.stdout.write(f"  → {linked} empty-description items handled\n")

    # ------------------------------------------------------------------
    def _fix_special_items(self, apply: bool):
        """
        Handle SalesItem rows that need quantity/price overrides or splitting.
        Runs BEFORE _auto_link so those rows get item set and won't be re-matched.
        """
        from inventory.models import Item
        from sales.models import SalesItem

        item_map: dict[str, object] = {}
        for item in Item.objects.filter(is_deleted=False):
            item_map[item.name.strip().lower()] = item

        self.stdout.write("Fixing special sales items (splits, qty/price overrides):")
        fixed = 0

        for desc_key, spec in SPECIAL_DESCRIPTIONS.items():
            rows = list(
                SalesItem.objects.filter(
                    item__isnull=True,
                    description__iexact=desc_key,
                )
            )
            if not rows:
                continue

            if spec["action"] == "link_override":
                target = item_map.get(spec["target"].strip().lower())
                if not target:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  WARNING: target '{spec['target']}' not found for '{desc_key}'"
                        )
                    )
                    continue
                for row in rows:
                    updates = {"item": target}
                    if "quantity" in spec:
                        updates["quantity"] = spec["quantity"]
                    if "price" in spec:
                        updates["final_price_per_unit"] = spec["price"]
                    if apply:
                        SalesItem.objects.filter(pk=row.pk).update(**updates)
                    verb = "Fixed" if apply else "Would fix"
                    qty = spec.get("quantity", row.quantity)
                    price = spec.get("price", row.final_price_per_unit)
                    self.stdout.write(
                        f"  {verb} SalesItem #{row.pk} '{desc_key}'"
                        f" → '{spec['target']}' (qty={qty}, price={price})"
                    )
                    fixed += 1

            elif spec["action"] == "split":
                for row in rows:
                    items_spec = spec["items"]
                    first = items_spec[0]
                    first_target = item_map.get(first["target"].strip().lower())
                    if not first_target:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  WARNING: target '{first['target']}' not found"
                            )
                        )
                        continue

                    if apply:
                        SalesItem.objects.filter(pk=row.pk).update(
                            item=first_target,
                            quantity=first["quantity"],
                            final_price_per_unit=first["price"],
                            description=first["target"],
                        )

                    verb = "Split" if apply else "Would split"
                    self.stdout.write(f"  {verb} SalesItem #{row.pk} '{desc_key}':")
                    self.stdout.write(
                        f"    → updated: {first['target']}"
                        f" (qty={first['quantity']}, price={first['price']})"
                    )

                    for extra in items_spec[1:]:
                        extra_target = item_map.get(extra["target"].strip().lower())
                        if not extra_target:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  WARNING: target '{extra['target']}' not found"
                                )
                            )
                            continue
                        if apply:
                            SalesItem.objects.create(
                                transaction_id=row.transaction_id,
                                item=extra_target,
                                quantity=extra["quantity"],
                                final_price_per_unit=extra["price"],
                                description=extra["target"],
                                line_discount_rate=Decimal("0"),
                            )
                        self.stdout.write(
                            f"    → created: {extra['target']}"
                            f" (qty={extra['quantity']}, price={extra['price']})"
                        )

                    fixed += 1

        self.stdout.write(f"  → {fixed} special items handled\n")

    # ------------------------------------------------------------------
    def _auto_link(self, apply: bool) -> tuple[int, list]:
        from inventory.models import Item
        from sales.models import SalesItem
        from services.models import ApplianceItemUsed, ServiceItemUsed

        # Build a lookup: normalised name → Item
        item_map: dict[str, object] = {}
        for item in Item.objects.filter(is_deleted=False):
            item_map[item.name.strip().lower()] = item

        # Build alias lookup: alias (lowercase) → Item
        alias_item_map: dict[str, object] = {}
        for alias_key, target_name in ALIAS_MAP.items():
            target = item_map.get(target_name.strip().lower())
            if target:
                alias_item_map[alias_key] = target
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ALIAS WARNING: target '{target_name}' not found for alias '{alias_key}'"
                    )
                )

        total_linked = 0
        unmatched_map: dict[str, list] = {}  # desc_lower → [count, avg_price]

        def _link_batch(qs, desc_field: str, price_field: str, label: str):
            nonlocal total_linked
            rows = list(qs.filter(item__isnull=True).exclude(**{desc_field: ""}))
            linked = 0
            for row in rows:
                desc = (getattr(row, desc_field) or "").strip()
                key = desc.lower()
                # Try exact match first, then alias
                match = item_map.get(key) or alias_item_map.get(key)
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

        self.stdout.write("Auto-linking by exact name match + aliases:")
        _link_batch(SalesItem.objects, "description", "final_price_per_unit", "SalesItem")
        _link_batch(ApplianceItemUsed.objects, "custom_description", "custom_price", "ApplianceItemUsed")
        _link_batch(ServiceItemUsed.objects, "custom_description", "custom_price", "ServiceItemUsed")

        # Build unmatched report
        unmatched = []
        for key, (desc, count, price_sum, price_count) in unmatched_map.items():
            avg = price_sum / price_count if price_count else None
            unmatched.append((desc, count, avg))

        return total_linked, unmatched
