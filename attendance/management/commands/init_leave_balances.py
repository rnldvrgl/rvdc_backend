from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from attendance.models import LeaveBalance
from datetime import date

User = get_user_model()


class Command(BaseCommand):
    help = 'Initialize leave balances for all active employees for a given year'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=date.today().year,
            help='Year to initialize leave balances for (default: current year)'
        )

    def handle(self, *args, **options):
        year = options['year']
        
        self.stdout.write(f'Initializing leave balances for year {year}...')
        
        active_employees = User.objects.filter(is_deleted=False, is_active=True)
        created_count = 0
        existing_count = 0
        
        for employee in active_employees:
            balance, created = LeaveBalance.objects.get_or_create(
                employee=employee,
                year=year,
                defaults={
                    'sick_leave_total': 5,
                    'emergency_leave_total': 5,
                    'sick_leave_used': 0,
                    'emergency_leave_used': 0,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created leave balance for {employee.get_full_name()}')
                )
            else:
                existing_count += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'\nSummary:\n'
            f'  Created: {created_count}\n'
            f'  Already exists: {existing_count}\n'
            f'  Total employees: {active_employees.count()}'
        ))
