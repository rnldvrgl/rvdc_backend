"""
Django management command to check if auto-close is enabled in PayrollSettings.

This command is used by cron scripts to determine whether to run
the auto_close_attendance command.

Usage:
    python manage.py check_auto_close_enabled

Returns:
    Exit code 0 if enabled
    Exit code 1 if disabled
    Prints "enabled" or "disabled" to stdout
"""

from django.core.management.base import BaseCommand
from payroll.models import PayrollSettings


class Command(BaseCommand):
    help = 'Check if auto-close attendance is enabled in PayrollSettings'

    def handle(self, *args, **options):
        try:
            settings = PayrollSettings.objects.first()

            if settings and settings.auto_close_enabled:
                self.stdout.write('enabled')
                return 0  # Success exit code
            else:
                self.stdout.write('disabled')
                return 1  # Failure exit code (will skip in cron)

        except Exception as e:
            self.stderr.write(f'Error checking settings: {e}')
            self.stdout.write('disabled')
            return 1  # Failure exit code on error
