
from django.core.management.base import BaseCommand
from inventory.models import Item, StockRoomStock


class Command(BaseCommand):
    help = "Create StockRoomStock records for all items"

    def handle(self, *args, **options):
        items = Item.objects.all()

        created = 0

        for item in items:
            obj, was_created = StockRoomStock.objects.get_or_create(
                item=item,
                defaults={"quantity": 0, "low_stock_threshold":5},
            )
            if was_created:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Created {created} stock records")
        )
