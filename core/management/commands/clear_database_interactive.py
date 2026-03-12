from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import transaction
import sys


class Command(BaseCommand):
    help = "Interactively clear database records (data) with custom selection. Table structures remain intact."

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto-yes',
            action='store_true',
            help='Automatically answer yes to final confirmation'
        )
        parser.add_argument(
            '--clear-all',
            action='store_true',
            help='Clear all transactional records without interactive selection'
        )

    def handle(self, *args, **options):
        # All available models with descriptions
        all_models = {
            # Transactional Data (DELETE by default)
            'sales.SalesTransaction': {'name': 'Sales Transactions', 'default': 'delete'},
            'sales.SalesItem': {'name': 'Sales Items', 'default': 'delete'},
            'sales.SalesPayment': {'name': 'Sales Payments', 'default': 'delete'},
            'services.Service': {'name': 'Services', 'default': 'delete'},
            'services.ServicePayment': {'name': 'Service Payments', 'default': 'delete'},
            'services.ServiceRefund': {'name': 'Service Refunds', 'default': 'delete'},

            'services.TechnicianAssignment': {'name': 'Technician Assignments', 'default': 'delete'},
            'services.ServiceAppliance': {'name': 'Service Appliances', 'default': 'delete'},

            'schedules.Schedule': {'name': 'Schedules', 'default': 'delete'},
            'schedules.ScheduleStatusHistory': {'name': 'Schedule Status History', 'default': 'delete'},
            'attendance.DailyAttendance': {'name': 'Attendance Records', 'default': 'delete'},
            'attendance.LeaveRequest': {'name': 'Leave Requests', 'default': 'delete'},
            'attendance.OvertimeRequest': {'name': 'Overtime Requests', 'default': 'delete'},
            'attendance.Offense': {'name': 'Offenses', 'default': 'delete'},
            'payroll.WeeklyPayroll': {'name': 'Payroll Records', 'default': 'delete'},
            'payroll.AdditionalEarning': {'name': 'Additional Earnings', 'default': 'delete'},
            'payroll.ManualDeduction': {'name': 'Manual Deductions', 'default': 'delete'},
            'remittances.RemittanceRecord': {'name': 'Remittance Records', 'default': 'delete'},
            'remittances.CashDenominationBreakdown': {'name': 'Cash Denomination Breakdowns', 'default': 'delete'},
            'receivables.ChequeCollection': {'name': 'Cheque Collections', 'default': 'delete'},
            
            # Master Data (PRESERVE by default)
            'clients.Client': {'name': 'Clients', 'default': 'preserve'},
            'inventory.Item': {'name': 'Inventory Items', 'default': 'preserve'},
            'inventory.Category': {'name': 'Item Categories', 'default': 'preserve'},
            'inventory.Stock': {'name': 'Stall Stock Records', 'default': 'preserve'},
            'inventory.StockRoomStock': {'name': 'Stock Room Inventory', 'default': 'preserve'},
            'inventory.Stall': {'name': 'Stalls', 'default': 'preserve'},
            'services.ApplianceType': {'name': 'Appliance Types', 'default': 'preserve'},
            'attendance.LeaveBalance': {'name': 'Leave Balances', 'default': 'preserve'},
            'payroll.PayrollSettings': {'name': 'Payroll Settings', 'default': 'preserve'},
            'payroll.Holiday': {'name': 'Holidays', 'default': 'preserve'},
            'payroll.GovernmentBenefit': {'name': 'Government Benefits', 'default': 'preserve'},
            'payroll.TaxBracket': {'name': 'Tax Brackets', 'default': 'preserve'},
            'payroll.DeductionRate': {'name': 'Deduction Rates', 'default': 'preserve'},
            'expenses.Expense': {'name': 'Expenses', 'default': 'preserve'},
            'expenses.ExpenseCategory': {'name': 'Expense Categories', 'default': 'preserve'},
            'expenses.ExpenseItem': {'name': 'Expense Items', 'default': 'preserve'},
            'users.CustomUser': {'name': 'Users', 'default': 'preserve'},
        }

        self.stdout.write(self.style.WARNING('\n' + '=' * 80))
        self.stdout.write(self.style.WARNING('INTERACTIVE DATABASE CLEANUP - Clear Records (Data) Only'))
        self.stdout.write(self.style.WARNING('Table structures will remain intact'))
        self.stdout.write(self.style.WARNING('=' * 80 + '\n'))

        if options['clear_all']:
            # Use default selections
            to_delete = {k: v for k, v in all_models.items() if v['default'] == 'delete'}
            to_preserve = {k: v for k, v in all_models.items() if v['default'] == 'preserve'}
        else:
            # Interactive selection
            self.stdout.write('Select which table records to DELETE (default selections are marked):')
            self.stdout.write('Type the number to toggle selection, "done" when finished\n')

            # Track selections (start with defaults)
            selections = {k: (v['default'] == 'delete') for k, v in all_models.items()}

            # Group by action
            transactional = [(k, v) for k, v in all_models.items() if v['default'] == 'delete']
            master_data = [(k, v) for k, v in all_models.items() if v['default'] == 'preserve']

            while True:
                self.stdout.write('\n' + '=' * 80)
                self.stdout.write(self.style.ERROR('Transactional Data (records will be DELETED by default):'))
                for idx, (model_path, info) in enumerate(transactional, 1):
                    selected = '✓' if selections[model_path] else ' '
                    self.stdout.write(f'  [{selected}] {idx}. {info["name"]} ({model_path})')

                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS('Master Data (records will be PRESERVED by default):'))
                for idx, (model_path, info) in enumerate(master_data, len(transactional) + 1):
                    selected = '✓' if selections[model_path] else ' '
                    self.stdout.write(f'  [{selected}] {idx}. {info["name"]} ({model_path})')

                self.stdout.write('\n' + '=' * 80)
                choice = input('\nEnter number to toggle (or "done" to proceed): ').strip().lower()

                if choice == 'done':
                    break

                try:
                    num = int(choice)
                    all_items = transactional + master_data
                    if 1 <= num <= len(all_items):
                        model_path = all_items[num - 1][0]
                        selections[model_path] = not selections[model_path]
                    else:
                        self.stdout.write(self.style.ERROR('Invalid number'))
                except ValueError:
                    self.stdout.write(self.style.ERROR('Invalid input'))

            to_delete = {k: v for k, v in all_models.items() if selections[k]}
            to_preserve = {k: v for k, v in all_models.items() if not selections[k]}

        # Show final selection
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('✓ Records in these tables will be PRESERVED:'))
        self.stdout.write('')
        for model_path, info in sorted(to_preserve.items()):
            self.stdout.write(f'  • {info["name"]} ({model_path})')

        self.stdout.write('')
        self.stdout.write(self.style.ERROR('✗ Records in these tables will be DELETED:'))
        self.stdout.write('')
        for model_path, info in sorted(to_delete.items()):
            try:
                app_label, model_name = model_path.split('.')
                model = apps.get_model(app_label, model_name)
                count = model.objects.count()
                self.stdout.write(f'  • {info["name"]} ({model_path}) - {count} records')
            except LookupError:
                self.stdout.write(f'  • {info["name"]} ({model_path}) - Model not found')
            except Exception as e:
                self.stdout.write(f'  • {info["name"]} ({model_path}) - Error: {str(e)}')

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write('')

        # Final confirmation
        if not options['auto_yes']:
            confirmation = input('Proceed with deletion? Type "yes" to confirm: ').strip().lower()
            
            if confirmation != 'yes':
                self.stdout.write(self.style.WARNING('Operation cancelled.'))
                sys.exit(0)

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Starting record deletion (table structures will remain)...'))
        self.stdout.write('')

        # Perform deletion
        deleted_count = 0
        error_count = 0
        total_records = 0

        with transaction.atomic():
            for model_path, info in sorted(to_delete.items()):
                try:
                    app_label, model_name = model_path.split('.')
                    model = apps.get_model(app_label, model_name)
                    count = model.objects.count()
                    
                    if count > 0:
                        model.objects.all().delete()
                        deleted_count += 1
                        total_records += count
                        self.stdout.write(
                            self.style.SUCCESS(f'  ✓ Deleted {count} records from {info["name"]}')
                        )
                    else:
                        self.stdout.write(f'  • No records in {info["name"]}')
                        
                except LookupError:
                    error_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠ Model not found: {model_path}')
                    )
                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Error deleting {info["name"]}: {str(e)}')
                    )

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.SUCCESS(f'\n✓ Record deletion complete!'))
        self.stdout.write(f'  • Tables cleared of data: {deleted_count}')
        self.stdout.write(f'  • Total records deleted: {total_records}')
        self.stdout.write(f'  • Errors: {error_count}')
        self.stdout.write(f'  • Tables with data preserved: {len(to_preserve)}')
        self.stdout.write(f'  • Note: All table structures remain intact')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('=' * 80 + '\n'))
