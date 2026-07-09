import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from inventory.models import Stall

User = get_user_model()


class Command(BaseCommand):
    help = "Creates default stalls and users, with roles and stall assignments"

    # Map username -> env var name holding that user's password.
    # Set these in .env.production / .env.local — never hardcode passwords in source.
    PASSWORD_ENV_VARS = {
        "rnldvrgl": "SEED_USER_RNLDVRGL_PASSWORD",
        "analyn1012": "SEED_USER_ANALYN1012_PASSWORD",
        "abigail": "SEED_USER_ABIGAIL_PASSWORD",
        "rosamae": "SEED_USER_ROSAMAE_PASSWORD",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help=(
                "Also reset passwords for users that already exist, using the "
                "current values from the environment. By default, passwords are "
                "only set when a user is first created."
            ),
        )

    def handle(self, *args, **options):
        reset_passwords = bool(options.get("reset_passwords"))

        self.stdout.write(self.style.WARNING('\n' + '=' * 80))
        self.stdout.write(self.style.WARNING('INITIALIZING DEFAULT STALLS AND USERS'))
        self.stdout.write(self.style.WARNING('=' * 80 + '\n'))

        # Step 1: Clean up duplicate stalls first
        self.stdout.write(self.style.WARNING('Step 1: Checking for duplicate stalls...'))

        main_stalls = Stall.objects.filter(name="Main").order_by('id')
        sub_stalls = Stall.objects.filter(name="Sub").order_by('id')

        if main_stalls.count() > 1:
            keep_main = main_stalls.first()
            duplicates = main_stalls.exclude(id=keep_main.id)
            count = duplicates.count()
            duplicates.delete()
            self.stdout.write(self.style.SUCCESS(f'  ✓ Removed {count} duplicate Main stall(s)'))

        if sub_stalls.count() > 1:
            keep_sub = sub_stalls.first()
            duplicates = sub_stalls.exclude(id=keep_sub.id)
            count = duplicates.count()
            duplicates.delete()
            self.stdout.write(self.style.SUCCESS(f'  ✓ Removed {count} duplicate Sub stall(s)'))

        if main_stalls.count() <= 1 and sub_stalls.count() <= 1:
            self.stdout.write('  • No duplicate stalls found')

        self.stdout.write('')

        # Step 2: Create or update default stalls
        self.stdout.write(self.style.WARNING('Step 2: Ensuring default stalls exist...'))

        default_stalls = [
            {
                "name": "Main",
                "location": "A-02 MRL Building, Mc. Arthur Hiway, Mabiga, Mabalacat City, Pampanga",
                "inventory_enabled": False,
                "is_system": True,
                "stall_type": "main",
            },
            {
                "name": "Sub",
                "location": "A-03 MRL Building, Mc. Arthur Hiway, Mabiga, Mabalacat City, Pampanga",
                "inventory_enabled": True,
                "is_system": True,
                "stall_type": "sub",
            },
        ]

        stall_map = {}

        for stall_data in default_stalls:
            stall, created = Stall.objects.update_or_create(
                name=stall_data["name"],
                defaults={
                    "location": stall_data["location"],
                    "inventory_enabled": stall_data["inventory_enabled"],
                    "is_system": stall_data["is_system"],
                    "stall_type": stall_data["stall_type"],
                }
            )
            stall_map[stall.name] = stall

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Created stall: {stall.name} at {stall.location}')
                )
            else:
                self.stdout.write(
                    f'  • Updated stall: {stall.name} at {stall.location}'
                )

        self.stdout.write('')

        # Step 3: Create users
        self.stdout.write(self.style.WARNING('Step 3: Creating/updating default users...'))
        self.stdout.write('')

        # NOTE: passwords are no longer hardcoded here. Each user's password is
        # read from its own environment variable (see PASSWORD_ENV_VARS above).
        # Set these in .env.production / .env.local, never commit them to source.
        default_users = [
            {
                "username": "rnldvrgl",
                "first_name": "Ronald Vergel",
                "last_name": "Dela Cruz",
                "role": "admin",
                "is_staff": True,
                "is_admin": True,
                "is_superuser": True,
            },
            {
                "username": "analyn1012",
                "first_name": "Analyn",
                "last_name": "Dela Cruz",
                "role": "admin",
                "is_staff": True,
                "is_admin": True,
                "is_superuser": False,
            },
            {
                "username": "abigail",
                "first_name": "Abigail Joy",
                "last_name": "Pare",
                "role": "manager",
                "assigned_stall": stall_map.get("Main"),
            },
            {
                "username": "rosamae",
                "first_name": "Rosa Mae",
                "last_name": "Repiso",
                "role": "clerk",
                "assigned_stall": stall_map.get("Sub"),
            },
        ]

        skipped_missing_password = []

        for user_data in default_users:
            username = user_data["username"]
            role = user_data["role"]
            first_name = user_data["first_name"]
            last_name = user_data["last_name"]
            assigned_stall = user_data.get("assigned_stall")

            password_env_var = self.PASSWORD_ENV_VARS.get(username)
            password = os.environ.get(password_env_var) if password_env_var else None

            if not password:
                self.stdout.write(
                    self.style.ERROR(
                        f'  ✗ Skipping "{username}": password env var '
                        f'"{password_env_var}" is not set.'
                    )
                )
                skipped_missing_password.append(username)
                continue

            # For admin: check if admin with same name already exists
            if role == "admin":
                existing_admin = User.objects.filter(
                    role="admin",
                    first_name=first_name,
                    last_name=last_name
                ).first()
                if existing_admin:
                    self.stdout.write(
                        f'  • Admin already exists: {existing_admin.username} ({first_name} {last_name})'
                    )
                    if reset_passwords:
                        existing_admin.set_password(password)
                        existing_admin.save(update_fields=["password"])
                        self.stdout.write(self.style.SUCCESS(f'    ↳ Password reset for {existing_admin.username}'))
                    continue

            # For clerk: check if a clerk with same name and stall already exists
            if role == "clerk":
                existing_clerk = User.objects.filter(
                    role="clerk",
                    first_name=first_name,
                    last_name=last_name,
                    assigned_stall=assigned_stall
                ).first()
                if existing_clerk:
                    self.stdout.write(
                        f'  • Clerk already exists: {existing_clerk.username} ({first_name} {last_name})'
                    )
                    if reset_passwords:
                        existing_clerk.set_password(password)
                        existing_clerk.save(update_fields=["password"])
                        self.stdout.write(self.style.SUCCESS(f'    ↳ Password reset for {existing_clerk.username}'))
                    continue

            # For manager: check if a manager with same name and stall already exists
            if role == "manager" and assigned_stall:
                existing_manager = User.objects.filter(
                    role="manager",
                    first_name=first_name,
                    last_name=last_name,
                    assigned_stall=assigned_stall
                ).first()
                if existing_manager:
                    self.stdout.write(
                        f'  • Manager already exists: {existing_manager.username} ({first_name} {last_name}) for {assigned_stall.name}'
                    )
                    if reset_passwords:
                        existing_manager.set_password(password)
                        existing_manager.save(update_fields=["password"])
                        self.stdout.write(self.style.SUCCESS(f'    ↳ Password reset for {existing_manager.username}'))
                    continue

            user_defaults = {
                "first_name": first_name,
                "last_name": last_name,
                "role": role,
            }

            if assigned_stall:
                user_defaults["assigned_stall"] = assigned_stall

            user, created = User.objects.get_or_create(
                username=username,
                defaults=user_defaults,
            )

            if created:
                user.set_password(password)
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Created user: {user.username} ({user.role})')
                )
            else:
                self.stdout.write(f'  • User exists: {user.username} ({user.role})')
                if reset_passwords:
                    user.set_password(password)
                    self.stdout.write(self.style.SUCCESS(f'    ↳ Password reset for {user.username}'))

            # Ensure optional fields (assigned_stall, permissions) are updated
            if assigned_stall and user.assigned_stall != assigned_stall:
                user.assigned_stall = assigned_stall

            if user.role != role:
                user.role = role

            user.is_staff = user_data.get("is_staff", False)
            user.is_admin = user_data.get("is_admin", False)
            user.is_superuser = user_data.get("is_superuser", False)
            user.save()

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.SUCCESS('\n✓ Initialization complete!'))
        self.stdout.write(f'  • Stalls: {len(stall_map)} (Main, Sub)')
        self.stdout.write(f'  • Users processed: {len(default_users)}')
        if skipped_missing_password:
            self.stdout.write(
                self.style.ERROR(
                    f'  • Skipped (missing password env var): {", ".join(skipped_missing_password)}'
                )
            )
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 80 + '\n'))
