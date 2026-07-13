from celery import shared_task
from django.core.management import call_command


@shared_task
def cleanup_archived_quotations():
    call_command(
        "cleanup_archived_quotations",
        days=14,
    )
