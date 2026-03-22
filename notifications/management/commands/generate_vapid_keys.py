"""
Generate a valid VAPID key pair for Web Push notifications.

Usage:
    python manage.py generate_vapid_keys

Copy the output into your .env / .env.production file.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate a VAPID key pair for Web Push notifications"

    def handle(self, *args, **options):
        try:
            from py_vapid import Vapid
        except ImportError:
            self.stderr.write(
                self.style.ERROR(
                    "py_vapid not available. It is bundled with pywebpush.\n"
                    "Run: pip install pywebpush"
                )
            )
            return

        vapid = Vapid()
        vapid.generate_keys()

        raw_priv = vapid.private_pem()
        raw_pub = vapid.public_key

        # Application server key is the raw uncompressed public point, base64url-encoded
        import base64

        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PublicFormat,
        )

        pub_raw = raw_pub.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        pub_b64 = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()

        # Private key is the raw 32-byte integer, base64url-encoded
        priv_numbers = vapid.private_key.private_numbers()
        priv_bytes = priv_numbers.private_value.to_bytes(32, "big")
        priv_b64 = base64.urlsafe_b64encode(priv_bytes).rstrip(b"=").decode()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("VAPID keys generated successfully!"))
        self.stdout.write("")
        self.stdout.write("Add these to your .env.production file:")
        self.stdout.write(self.style.WARNING(f"VAPID_PUBLIC_KEY={pub_b64}"))
        self.stdout.write(self.style.WARNING(f"VAPID_PRIVATE_KEY={priv_b64}"))
        self.stdout.write(self.style.WARNING("VAPID_ADMIN_EMAIL=admin@rvdc.com"))
        self.stdout.write("")
        self.stdout.write(
            self.style.NOTICE(
                "IMPORTANT: After updating the keys, all existing push subscriptions "
                "become invalid. Users will automatically re-subscribe on next page load."
            )
        )
