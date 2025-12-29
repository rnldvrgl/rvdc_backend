
from django.core.management.base import BaseCommand
from inventory.models import Item, Stall, Stock


class Command(BaseCommand):
    help = "Create SStock records for all items in the Sub Stall"

    def handle(self, *args, **options):
        try:
            sub_stall = Stall.objects.get(name="Sub")
        except Stall.DoesNotExist:
            self.stderr.write(self.style.ERROR("❌ Sub Stall not found"))
            return

        items = Item.objects.all()

        if not items.exists():
            self.stdout.write(self.style.WARNING("⚠️ No items found"))
            return

        created_count = 0
        skipped_count = 0

        for item in items:
            stock_record, created = Stock.objects.get_or_create(
                stall=sub_stall,
                item=item,
                defaults={
                    "quantity": 0,
                    "low_stock_threshold": 5,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Created stock for {item.name}")
                )
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f"⚠️ Stock already exists for {item.name}")
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created_count}, Skipped: {skipped_count}"
            )
        )
