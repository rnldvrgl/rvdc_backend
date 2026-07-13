from celery import shared_task
from django.core.management import call_command


@shared_task
def delete_old_notifications():
    call_command(
        "delete_old_notifications",
        all=True,
        days=7,
    )
