from calendar import monthrange
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.models import Stall
from notifications.business_logic import notify_admins
from notifications.models import NotificationType
from sales.models import StallMonthlySheet


class Command(BaseCommand):
    help = "Notify admins when a next-month Google Sheet link is missing per stall."

    def add_arguments(self, parser):
        parser.add_argument(
            "--today",
            dest="today",
            default="",
            help="Override local date in YYYY-MM-DD format for testing.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run reminder checks even if today is not the month end.",
        )

    def handle(self, *args, **options):
        today_override = (options.get("today") or "").strip()
        force = bool(options.get("force"))

        if today_override:
            try:
                today = date.fromisoformat(today_override)
            except ValueError:
                self.stderr.write(self.style.ERROR("Invalid --today value. Use YYYY-MM-DD."))
                return
        else:
            today = timezone.localdate()

        last_day = monthrange(today.year, today.month)[1]
        if not force and today.day != last_day:
            self.stdout.write(
                f"Skipping reminders. Today {today} is not month-end (last day is {last_day})."
            )
            return

        next_month_seed = today.replace(day=28) + timedelta(days=4)
        next_month_date = next_month_seed.replace(day=1)
        next_month_key = next_month_date.strftime("%Y-%m")

        stalls = Stall.objects.filter(is_deleted=False).order_by("name")
        missing_stalls = []

        for stall in stalls:
            exists = StallMonthlySheet.objects.filter(
                stall=stall,
                month_key=next_month_key,
                is_active=True,
            ).exists()
            if not exists:
                missing_stalls.append(stall)

        if not missing_stalls:
            self.stdout.write(self.style.SUCCESS(f"All stalls have monthly sheet links for {next_month_key}."))
            return

        for stall in missing_stalls:
            notify_admins(
                NotificationType.SYSTEM_ALERT,
                title=f"Missing Google Sheet Link: {stall.name} ({next_month_key})",
                message=(
                    f"No active Google Sheet link is configured for stall '{stall.name}' "
                    f"for month {next_month_key}. Add it in Sales > Monthly Sheets settings."
                ),
                data={
                    "stall_id": stall.id,
                    "stall_name": stall.name,
                    "month_key": next_month_key,
                    "type": "missing_monthly_google_sheet",
                },
            )

        self.stdout.write(
            self.style.WARNING(
                f"Created {len(missing_stalls)} admin reminder(s) for missing {next_month_key} links."
            )
        )
