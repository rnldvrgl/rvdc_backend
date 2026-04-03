from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import transaction
import sys


class Command(BaseCommand):
    help = "Clear database records (data) while preserving important data. Table structures remain intact."

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto-yes',
            action='store_true',
            help='Automatically answer yes to confirmation prompt'
        )

    def handle(self, *args, **options):
        # Data to PRESERVE by default
        # These are critical business records that should not be deleted
        preserve_models = {
            'clients.Client': 'Clients',
            'inventory.Item': 'Inventory Items',
            'inventory.Category': 'Item Categories',
            'inventory.StallStock': 'Stall Stock Records',
            'inventory.StockRoomStock': 'Stock Room Inventory',
            'inventory.Stall': 'Stalls',
            'services.ApplianceType': 'Appliance Types',
            'attendance.LeaveBalance': 'Leave Balances',
            'payroll.PayrollSettings': 'Payroll Settings',
            'payroll.Holiday': 'Holidays',
            'payroll.GovernmentBenefit': 'Government Benefits',
            'payroll.DeductionRate': 'Deduction Rates',
            'expenses.Expense': 'Expenses',
            'expenses.ExpenseCategory': 'Expense Categories',
            'users.CustomUser': 'Users',
            'auth.Permission': 'Permissions',
            'contenttypes.ContentType': 'Content Types',
        }

        # Data to DELETE by default
        # Transactional records that can be safely cleared
        delete_models = {
            'sales.SalesTransaction': 'Sales Transactions',
            'sales.SalesItem': 'Sales Items',
            'sales.SalesPayment': 'Sales Payments',
            'services.Service': 'Services',
            'services.ServicePayment': 'Service Payments',
            'services.ServiceRefund': 'Service Refunds',

            'services.TechnicianAssignment': 'Technician Assignments',
            'services.ServiceAppliance': 'Service Appliances',

            'schedules.Schedule': 'Schedules',
            'schedules.ScheduleStatusHistory': 'Schedule Status History',
            'attendance.DailyAttendance': 'Attendance Records',
            'attendance.LeaveRequest': 'Leave Requests',
            'attendance.OvertimeRequest': 'Overtime Requests',
            'attendance.Offense': 'Offenses',
            'payroll.WeeklyPayroll': 'Payroll Records',
            'payroll.AdditionalEarning': 'Additional Earnings',
            'payroll.ManualDeduction': 'Manual Deductions',
            'remittances.RemittanceRecord': 'Remittance Records',
            'remittances.CashDenominationBreakdown': 'Cash Denomination Breakdowns',
            'receivables.ChequeCollection': 'Cheque Collections',
        }

        self.stdout.write(self.style.WARNING('\n' + '=' * 80))
        self.stdout.write(self.style.WARNING('DATABASE CLEANUP - Clear Records (Data) Only'))
        self.stdout.write(self.style.WARNING('Table structures will remain intact'))
        self.stdout.write(self.style.WARNING('=' * 80 + '\n'))

        self.stdout.write(self.style.SUCCESS('✓ Records in these tables will be PRESERVED:'))
        self.stdout.write('')
        for model_path, description in sorted(preserve_models.items()):
            self.stdout.write(f'  • {description} ({model_path})')

        self.stdout.write('')
        self.stdout.write(self.style.ERROR('✗ Records in these tables will be DELETED:'))
        self.stdout.write('')
        for model_path, description in sorted(delete_models.items()):
            try:
                app_label, model_name = model_path.split('.')
                model = apps.get_model(app_label, model_name)
                count = model.objects.count()
                self.stdout.write(f'  • {description} ({model_path}) - {count} records')
            except LookupError:
                self.stdout.write(f'  • {description} ({model_path}) - Model not found')
            except Exception as e:
                self.stdout.write(f'  • {description} ({model_path}) - Error: {str(e)}')

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write('')

        # Ask for confirmation
        if not options['auto_yes']:
            confirmation = input('Are you sure you want to DELETE the above records? Type "yes" or "no": ').strip().lower()

            if confirmation not in ['yes', 'y']:
                self.stdout.write(self.style.WARNING('Operation cancelled.'))
                sys.exit(0)

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Starting record deletion (table structures will remain)...'))
        self.stdout.write('')

        # Perform deletion in a transaction
        deleted_count = 0
        error_count = 0

        with transaction.atomic():
            for model_path, description in sorted(delete_models.items()):
                try:
                    app_label, model_name = model_path.split('.')
                    model = apps.get_model(app_label, model_name)
                    count = model.objects.count()

                    if count > 0:
                        model.objects.all().delete()
                        deleted_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'  ✓ Deleted {count} records from {description}')
                        )
                    else:
                        self.stdout.write(f'  • No records to delete from {description}')

                except LookupError:
                    error_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠ Model not found: {model_path}')
                    )
                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Error deleting {description}: {str(e)}')
                    )

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.SUCCESS(f'\n✓ Record deletion complete!'))
        self.stdout.write(f'  • Tables cleared of data: {deleted_count}')
        self.stdout.write(f'  • Errors: {error_count}')
        self.stdout.write(f'  • Tables with data preserved: {len(preserve_models)}')
        self.stdout.write(f'  • Note: All table structures remain intact')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 80 + '\n'))
