from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Creates default users with predefined roles"

    def handle(self, *args, **options):
        default_users = [
            {
                "username": "rnldvrgl",
                "password": "daizuke0908",
                "first_name": "Ronald Vergel",
                "last_name": "Dela Cruz",
                "role": "admin",
            },
            {
                "username": "analyn1012",
                "password": "ladylibra101282",
                "first_name": "Analyn",
                "last_name": "Dela Cruz",
                "role": "admin",
            },
            {
                "username": "abigail",
                "password": "rvdc12",
                "first_name": "Abigail Joy",
                "last_name": "Pare",
                "role": "manager",
            },
            {
                "username": "rosamae",
                "password": "rvdc12",
                "first_name": "Rosa Mae",
                "last_name": "Repiso",
                "role": "clerk",
            },
        ]

        for user_data in default_users:
            user, created = User.objects.get_or_create(
                username=user_data["username"],
                defaults={
                    "first_name": user_data["first_name"],
                    "last_name": user_data["last_name"],
                    "role": user_data["role"],  # assuming you have a 'role' field
                },
            )
            if created:
                user.set_password(user_data["password"])
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Created: {user.username} ({user.role})")
                )
            else:
                self.stdout.write(f"⚠️ Exists: {user.username} ({user.role})")
