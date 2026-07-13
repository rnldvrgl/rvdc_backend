from celery import shared_task
from django.core.management import call_command


@shared_task
def cleanup_unused_images():
    call_command("cleanup_unused_images")


@shared_task
def create_leave_balances():
    call_command("create_leave_balances")
