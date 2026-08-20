from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Run ANALYZE on the database or a specific table."

    def add_arguments(self, parser):
        parser.add_argument("--table", help="Optional table name to analyze", default=None)

    def handle(self, *args, **options):
        table = options["table"]
        with connection.cursor() as cur:
            if table:
                cur.execute(f'ANALYZE "{table}";')
            else:
                cur.execute("ANALYZE;")

        self.stdout.write(self.style.SUCCESS("ANALYZE completed."))
