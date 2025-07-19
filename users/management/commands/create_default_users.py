from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from inventory.models import Stall

User = get_user_model()


class Command(BaseCommand):
    help = "Creates default stalls and users, with roles and stall assignments"

    def handle(self, *args, **options):
        # Step 1: Create default stalls
        default_stalls = [
            {"name": "Main Stall", "location": "A-02"},
            {"name": "Sub Stall", "location": "A-03"},
        ]

        stall_map = {}

        for stall_data in default_stalls:
            stall, created = Stall.objects.get_or_create(**stall_data)
            stall_map[stall.name] = stall
            msg = (
                f"🏪 Created Stall: {stall.name}"
                if created
                else f"🏪 Stall exists: {stall.name}"
            )
            self.stdout.write(self.style.SUCCESS(msg) if created else msg)

        # Step 2: Create users
        default_users = [
            {
                "username": "rnldvrgl",
                "password": "daizuke0908",
                "first_name": "Ronald Vergel",
                "last_name": "Dela Cruz",
                "role": "admin",
                "is_staff": True,
                "is_admin": True,
                "is_superuser": True,
            },
            {
                "username": "analyn1012",
                "password": "ladylibra101282",
                "first_name": "Analyn",
                "last_name": "Dela Cruz",
                "role": "admin",
                "is_staff": True,
                "is_admin": True,
                "is_superuser": False,
            },
            {
                "username": "abigail",
                "password": "rvdc12",
                "first_name": "Abigail Joy",
                "last_name": "Pare",
                "role": "manager",
                "assigned_stall": stall_map.get("Main Stall"),
            },
            {
                "username": "rosamae",
                "password": "rvdc12",
                "first_name": "Rosa Mae",
                "last_name": "Repiso",
                "role": "clerk",
                "assigned_stall": stall_map.get("Sub Stall"),
            },
        ]

        for user_data in default_users:
            username = user_data["username"]
            user_defaults = {
                "first_name": user_data["first_name"],
                "last_name": user_data["last_name"],
                "role": user_data["role"],
            }

            # Optional fields
            if "assigned_stall" in user_data:
                user_defaults["assigned_stall"] = user_data["assigned_stall"]

            user, created = User.objects.get_or_create(
                username=username,
                defaults=user_defaults,
            )

            if created:
                user.set_password(user_data["password"])
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Created: {user.username} ({user.role})")
                )
            else:
                self.stdout.write(f"⚠️ Exists: {user.username} ({user.role})")

            # Ensure optional fields (assigned_stall, permissions) are updated
            updated = False

            if (
                "assigned_stall" in user_data
                and user.assigned_stall != user_data["assigned_stall"]
            ):
                user.assigned_stall = user_data["assigned_stall"]
                updated = True

            # Apply role-based permissions
            user.is_staff = user_data.get("is_staff", False)
            user.is_admin = user_data.get("is_admin", False)
            user.is_superuser = user_data.get("is_superuser", False)
            updated = True

            if updated:
                user.save()
