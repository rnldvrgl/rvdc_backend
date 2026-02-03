"""
Management command to create leave balances for existing employees.
This is useful for migrating existing data after adding the leave balance feature.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import CustomUser
from attendance.models import LeaveBalance


class Command(BaseCommand):
    help = 'Create leave balances for existing technicians, managers, and clerks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=timezone.now().year,
            help='Year to create leave balances for (default: current year)'
        )

    def handle(self, *args, **options):
        year = options['year']
        eligible_roles = ['technician', 'manager', 'clerk']
        
        # Get all employees with eligible roles
        employees = CustomUser.objects.filter(
            role__in=eligible_roles,
            is_deleted=False
        )
        
        created_count = 0
        skipped_count = 0
        
        for employee in employees:
            # Check if leave balance already exists
            if LeaveBalance.objects.filter(employee=employee, year=year).exists():
                self.stdout.write(
                    self.style.WARNING(
                        f'Skipped {employee.get_full_name()} ({employee.role}) - '
                        f'leave balance for {year} already exists'
                    )
                )
                skipped_count += 1
                continue
            
            # Create leave balance
            LeaveBalance.objects.create(
                employee=employee,
                year=year,
                sick_leave_total=5,
                sick_leave_used=0,
                emergency_leave_total=5,
                emergency_leave_used=0
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Created leave balance for {employee.get_full_name()} ({employee.role})'
                )
            )
            created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary:\n'
                f'  Created: {created_count}\n'
                f'  Skipped: {skipped_count}\n'
                f'  Total employees: {employees.count()}'
            )
        )
