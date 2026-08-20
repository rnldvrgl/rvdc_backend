from django.core.management.base import BaseCommand
from django.core.cache import cache


class Command(BaseCommand):
    help = "Clear the Django cache (useful for development)."

    def handle(self, *args, **options):
        try:
            cache.clear()
            self.stdout.write(self.style.SUCCESS("Cache cleared."))
        except Exception as e:
            self.stderr.write(str(e))
            raise
