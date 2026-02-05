from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from inventory.models import Stall

User = get_user_model()


class Command(BaseCommand):
    help = "Creates default stalls and users, with roles and stall assignments"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('\n' + '=' * 80))
        self.stdout.write(self.style.WARNING('INITIALIZING DEFAULT STALLS AND USERS'))
        self.stdout.write(self.style.WARNING('=' * 80 + '\n'))
        
        # Step 1: Clean up duplicate stalls first
        self.stdout.write(self.style.WARNING('Step 1: Checking for duplicate stalls...'))
        
        # Find all stalls named "Main" or "Sub"
        main_stalls = Stall.objects.filter(name="Main").order_by('id')
        sub_stalls = Stall.objects.filter(name="Sub").order_by('id')
        
        # Keep only the first one of each, delete others
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
            },
            {
                "name": "Sub",
                "location": "A-03 MRL Building, Mc. Arthur Hiway, Mabiga, Mabalacat City, Pampanga",
                "inventory_enabled": True,
                "is_system": True,
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
        
        # Step 3: Create users
        self.stdout.write(self.style.WARNING('Step 3: Creating/updating default users...'))
        
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
                "assigned_stall": stall_map.get("Main"),
            },
            {
                "username": "hgl",
                "password": "rvdc12",
                "first_name": "Honey Grace",
                "last_name": "Labasan",
                "role": "clerk",
                "assigned_stall": stall_map.get("Sub"),
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
                    self.style.SUCCESS(f'  ✓ Created user: {user.username} ({user.role})')
                )
            else:
                self.stdout.write(f'  • User exists: {user.username} ({user.role})')

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
        
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.SUCCESS('\n✓ Initialization complete!'))
        self.stdout.write(f'  • Stalls: {len(stall_map)} (Main, Sub)')
        self.stdout.write(f'  • Users: {len(default_users)}')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 80 + '\n'))
