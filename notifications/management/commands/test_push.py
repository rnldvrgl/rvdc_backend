"""
Send a test Web Push notification to verify the setup is working.

Usage:
    python manage.py test_push <user_id>
    python manage.py test_push 1
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send a test Web Push notification to a user"

    def add_arguments(self, parser):
        parser.add_argument("user_id", type=int, help="Target user PK")

    def handle(self, *args, **options):
        user_id = options["user_id"]

        from notifications.models import PushSubscription

        subs = PushSubscription.objects.filter(user_id=user_id)
        count = subs.count()
        if count == 0:
            self.stderr.write(
                self.style.ERROR(f"No push subscriptions found for user {user_id}")
            )
            return

        self.stdout.write(f"Found {count} subscription(s) for user {user_id}")

        for sub in subs:
            self.stdout.write(f"  - Sub {sub.id}: {sub.endpoint[:80]}…")

        from notifications.push import send_web_push

        self.stdout.write("Sending test push…")
        send_web_push(
            user_id=user_id,
            title="Test Notification",
            body="If you see this, Web Push is working!",
            url="/",
            tag="test",
        )
        self.stdout.write(self.style.SUCCESS("Done. Check docker logs for result."))
