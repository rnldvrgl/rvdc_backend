"""
Management command to setup stalls and fix user assignments.

This command ensures that:
1. Main and Sub stalls exist as system stalls
2. All users (managers/clerks) have proper stall assignments
3. Orphaned users get assigned to appropriate stalls

Usage:
    python manage.py setup_stalls
    python manage.py setup_stalls --reset  # Reset and recreate stalls
"""

from django.core.management.base import BaseCommand
from users.models import CustomUser

from inventory.models import Stall


class Command(BaseCommand):
    help = 'Setup stalls and fix user stall assignments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset stalls and recreate them (WARNING: Only use in development)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        reset = options.get('reset', False)
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made\n')
            )

        self.stdout.write(self.style.SUCCESS('=== Stall Setup & User Assignment Fix ===\n'))

        # Step 1: Check current stalls
        self.stdout.write('Step 1: Checking current stalls...')
        stalls = Stall.objects.filter(is_deleted=False)

        self.stdout.write(f'  Found {stalls.count()} active stall(s):')
        for stall in stalls:
            self.stdout.write(
                f'    - ID: {stall.id}, Name: {stall.name}, Type: {stall.stall_type}, '
                f'System: {stall.is_system}, Inventory: {stall.inventory_enabled}'
            )

        # Step 2: Detect existing stalls from user assignments
        self.stdout.write('\nStep 2: Detecting stalls from existing user assignments...')

        # Find stalls that managers are currently assigned to
        manager_stalls = Stall.objects.filter(
            assigned_users__role='manager',
            is_deleted=False
        ).distinct()

        # Find stalls that clerks are currently assigned to
        clerk_stalls = Stall.objects.filter(
            assigned_users__role='clerk',
            is_deleted=False
        ).distinct()

        if manager_stalls.exists():
            self.stdout.write(f'  Found {manager_stalls.count()} stall(s) assigned to managers')
            for s in manager_stalls:
                self.stdout.write(f'    - ID: {s.id}, Name: {s.name}')

        if clerk_stalls.exists():
            self.stdout.write(f'  Found {clerk_stalls.count()} stall(s) assigned to clerks')
            for s in clerk_stalls:
                self.stdout.write(f'    - ID: {s.id}, Name: {s.name}')

        # Use existing manager stall as Main, or find/create one
        main_stall = stalls.filter(stall_type='main', is_system=True).first()

        if not main_stall and manager_stalls.exists():
            # Use the first manager stall as Main
            main_stall = manager_stalls.first()
            if not dry_run:
                main_stall.stall_type = 'main'
                main_stall.is_system = True
                main_stall.inventory_enabled = False
                if 'main' not in main_stall.name.lower():
                    main_stall.name = 'Main Stall'
                main_stall.save()
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Updated existing stall (ID: {main_stall.id}) to Main Stall')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'  [DRY RUN] Would update stall ID {main_stall.id} to Main Stall')
                )
        elif not main_stall:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING('  [DRY RUN] Would create Main Stall')
                )
            else:
                main_stall = Stall.objects.create(
                    name='Main Stall',
                    location='Services',
                    stall_type='main',
                    is_system=True,
                    inventory_enabled=False,
                )
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Created Main Stall (ID: {main_stall.id})')
                )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Main Stall exists (ID: {main_stall.id})')
            )

        # Use existing clerk stall as Sub, or find/create one
        sub_stall = stalls.filter(stall_type='sub', is_system=True).first()

        if not sub_stall and clerk_stalls.exists():
            # Use the first clerk stall as Sub
            sub_stall = clerk_stalls.first()
            if not dry_run:
                sub_stall.stall_type = 'sub'
                sub_stall.is_system = True
                sub_stall.inventory_enabled = True
                if 'sub' not in sub_stall.name.lower():
                    sub_stall.name = 'Sub Stall'
                sub_stall.save()
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Updated existing stall (ID: {sub_stall.id}) to Sub Stall')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'  [DRY RUN] Would update stall ID {sub_stall.id} to Sub Stall')
                )
        elif not sub_stall:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING('  [DRY RUN] Would create Sub Stall')
                )
            else:
                sub_stall = Stall.objects.create(
                    name='Sub Stall',
                    location='Parts & Inventory',
                    stall_type='sub',
                    is_system=True,
                    inventory_enabled=True,
                )
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Created Sub Stall (ID: {sub_stall.id})')
                )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Sub Stall exists (ID: {sub_stall.id})')
            )

        # Step 3: Check user assignments
        self.stdout.write('\nStep 3: Checking user stall assignments...')

        users = CustomUser.objects.filter(is_active=True)
        admins = users.filter(role='admin')
        managers = users.filter(role='manager')
        clerks = users.filter(role='clerk')

        self.stdout.write(f'  Total active users: {users.count()}')
        self.stdout.write(f'    - Admins: {admins.count()}')
        self.stdout.write(f'    - Managers: {managers.count()}')
        self.stdout.write(f'    - Clerks: {clerks.count()}')

        # Step 4: Fix assignments
        self.stdout.write('\nStep 4: Fixing user stall assignments...')

        fixed_count = 0

        # Managers and Clerks need stall assignments
        for user in managers:
            if not user.assigned_stall or user.assigned_stall.is_deleted:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  [DRY RUN] Would assign {user.username} (Manager) to Main Stall (ID: {main_stall.id if main_stall else "N/A"})'
                        )
                    )
                else:
                    if main_stall:
                        user.assigned_stall = main_stall
                        user.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ Assigned {user.username} (Manager) to Main Stall (ID: {main_stall.id})'
                            )
                        )
                        fixed_count += 1
            else:
                # Check if assigned to correct stall type
                if user.assigned_stall != main_stall and main_stall:
                    if dry_run:
                        self.stdout.write(
                            self.style.WARNING(
                                f'  [DRY RUN] Would reassign {user.username} (Manager) from {user.assigned_stall.name} to Main Stall'
                            )
                        )
                    else:
                        old_stall = user.assigned_stall.name
                        user.assigned_stall = main_stall
                        user.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ Reassigned {user.username} (Manager) from {old_stall} to Main Stall (ID: {main_stall.id})'
                            )
                        )
                        fixed_count += 1
                else:
                    self.stdout.write(
                        f'  ✓ {user.username} (Manager) correctly assigned to {user.assigned_stall.name} (ID: {user.assigned_stall.id})'
                    )

        for user in clerks:
            if not user.assigned_stall or user.assigned_stall.is_deleted:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  [DRY RUN] Would assign {user.username} (Clerk) to Sub Stall (ID: {sub_stall.id if sub_stall else "N/A"})'
                        )
                    )
                else:
                    if sub_stall:
                        user.assigned_stall = sub_stall
                        user.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ Assigned {user.username} (Clerk) to Sub Stall (ID: {sub_stall.id})'
                            )
                        )
                        fixed_count += 1
            else:
                # Check if assigned to correct stall type
                if user.assigned_stall != sub_stall and sub_stall:
                    if dry_run:
                        self.stdout.write(
                            self.style.WARNING(
                                f'  [DRY RUN] Would reassign {user.username} (Clerk) from {user.assigned_stall.name} to Sub Stall'
                            )
                        )
                    else:
                        old_stall = user.assigned_stall.name
                        user.assigned_stall = sub_stall
                        user.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ Reassigned {user.username} (Clerk) from {old_stall} to Sub Stall (ID: {sub_stall.id})'
                            )
                        )
                        fixed_count += 1
                else:
                    self.stdout.write(
                        f'  ✓ {user.username} (Clerk) correctly assigned to {user.assigned_stall.name} (ID: {user.assigned_stall.id})'
                    )

        # Admins don't need stall assignments (they see all)
        for user in admins:
            if user.assigned_stall:
                self.stdout.write(
                    self.style.WARNING(
                        f'  ⚠ {user.username} (Admin) has stall assignment: {user.assigned_stall.name} '
                        f'(Admins typically don\'t need assignments)'
                    )
                )

        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('Summary:'))
        self.stdout.write(f'  Active stalls: {Stall.objects.filter(is_deleted=False).count()}')
        self.stdout.write(f'  Main Stall ID: {main_stall.id if main_stall and not dry_run else "N/A"}')
        self.stdout.write(f'  Sub Stall ID: {sub_stall.id if sub_stall and not dry_run else "N/A"}')

        if dry_run:
            self.stdout.write(self.style.WARNING('  Users that would be fixed: (run without --dry-run to apply)'))
        else:
            self.stdout.write(self.style.SUCCESS(f'  Users fixed: {fixed_count}'))

        self.stdout.write('=' * 60)

        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nDRY RUN COMPLETE - No changes were made')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('\n✓ Stall setup and user assignment fix complete!')
            )

        # Step 5: Verification
        self.stdout.write('\nStep 5: Verification...')

        # Check for users without stalls
        managers_without_stalls = CustomUser.objects.filter(
            role='manager',
            assigned_stall__isnull=True,
            is_active=True
        ).count()

        clerks_without_stalls = CustomUser.objects.filter(
            role='clerk',
            assigned_stall__isnull=True,
            is_active=True
        ).count()

        if managers_without_stalls > 0:
            self.stdout.write(
                self.style.ERROR(
                    f'  ✗ {managers_without_stalls} manager(s) still without stall assignment!'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('  ✓ All managers have stall assignments')
            )

        if clerks_without_stalls > 0:
            self.stdout.write(
                self.style.ERROR(
                    f'  ✗ {clerks_without_stalls} clerk(s) still without stall assignment!'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('  ✓ All clerks have stall assignments')
            )

        # Recommendations
        self.stdout.write('\nRecommendations:')
        self.stdout.write('  1. Verify user assignments in Django admin or API')
        self.stdout.write('  2. Test expense creation with manager/clerk accounts')
        self.stdout.write('  3. Ensure role-based filtering works correctly')
        self.stdout.write('  4. Check that managers see only their stall\'s data')
