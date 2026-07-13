from celery import shared_task
from django.core.management import call_command


@shared_task
def add_philippine_holidays():
    call_command(
        "add_philippine_holidays",
        skip_existing=True,
    )


@shared_task
def archive_old_payrolls():
    call_command("archive_old_payrolls")


@shared_task
def update_holiday_years():
    call_command("update_holiday_years")
