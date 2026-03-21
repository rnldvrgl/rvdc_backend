"""
Django management command to fix SHOP_CLOSED attendance records where employees
actually worked (have clock_in/clock_out) but the system marked them as SHOP_CLOSED
before the WorkRequest feature existed.

This command:
1. Finds SHOP_CLOSED attendance with clock_in/clock_out (employee actually worked)
2. Creates an approved WorkRequest so the system recognizes the day as worked
3. Recalculates attendance metrics treating it as a normal working day

Usage:
    # Dry run — show what would be fixed
    python manage.py fix_shop_closed_attendance --dry-run

    # Fix a specific employee and date
    python manage.py fix_shop_closed_attendance --employee "Loreto Carunongan" --date 2026-03-15

    # Fix a specific employee (all their SHOP_CLOSED records with clock times)
    python manage.py fix_shop_closed_attendance --employee "Loreto Carunongan"

    # Fix all SHOP_CLOSED records that have clock_in/clock_out
    python manage.py fix_shop_closed_attendance --all

    # Fix by attendance ID
    python manage.py fix_shop_closed_attendance --ids 123,456
"""

from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from attendance.models import DailyAttendance, WorkRequest
from users.models import CustomUser


class Command(BaseCommand):
    help = (
        'Fix SHOP_CLOSED attendance records where an employee actually worked '
        '(has clock_in/clock_out) before the WorkRequest feature existed.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--employee',
            type=str,
            help='Employee full name (e.g. "Loreto Carunongan")',
        )
        parser.add_argument(
            '--employee-id',
            type=int,
            help='Employee ID',
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Specific date to fix (YYYY-MM-DD)',
        )
        parser.add_argument(
            '--ids',
            type=str,
            help='Comma-separated attendance IDs to fix',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            dest='fix_all',
            help='Fix ALL SHOP_CLOSED records that have clock_in/clock_out',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        employee_name = options['employee']
        employee_id = options['employee_id']
        target_date = options['date']
        attendance_ids = options['ids']
        fix_all = options['fix_all']

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('FIX SHOP_CLOSED ATTENDANCE (Employee Worked)'))
        self.stdout.write(self.style.SUCCESS('=' * 80))

        # Build queryset: SHOP_CLOSED with actual clock times
        queryset = DailyAttendance.objects.filter(
            attendance_type='SHOP_CLOSED',
            clock_in__isnull=False,
            clock_out__isnull=False,
            is_deleted=False,
        )

        if attendance_ids:
            ids_list = [int(x.strip()) for x in attendance_ids.split(',')]
            queryset = queryset.filter(id__in=ids_list)
            self.stdout.write(f"Targeting attendance IDs: {ids_list}")
        elif employee_name or employee_id or target_date:
            if employee_name:
                parts = employee_name.strip().split()
                if len(parts) >= 2:
                    queryset = queryset.filter(
                        employee__first_name__iexact=parts[0],
                        employee__last_name__iexact=' '.join(parts[1:]),
                    )
                else:
                    queryset = queryset.filter(
                        Q(employee__first_name__iexact=employee_name)
                        | Q(employee__last_name__iexact=employee_name)
                    )
                self.stdout.write(f"Targeting employee: {employee_name}")

            if employee_id:
                queryset = queryset.filter(employee_id=employee_id)
                self.stdout.write(f"Targeting employee ID: {employee_id}")

            if target_date:
                date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
                queryset = queryset.filter(date=date_obj)
                self.stdout.write(f"Targeting date: {target_date}")
        elif not fix_all:
            self.stdout.write(self.style.ERROR(
                '\nError: Specify --employee, --date, --ids, or --all to select records.'
            ))
            return

        attendances = queryset.order_by('date', 'employee__first_name')
        total = attendances.count()

        if total == 0:
            self.stdout.write(self.style.WARNING(
                '\nNo SHOP_CLOSED attendance records with clock times found.'
            ))
            return

        self.stdout.write(f"\nFound {total} record(s) to fix:\n")
        for att in attendances:
            tz = timezone.get_current_timezone()
            ci = att.clock_in.astimezone(tz).strftime('%I:%M %p') if att.clock_in else '-'
            co = att.clock_out.astimezone(tz).strftime('%I:%M %p') if att.clock_out else '-'
            self.stdout.write(
                f"  ID {att.id}: {att.employee.get_full_name()} | "
                f"{att.date} | {ci} - {co} | "
                f"paid_hours={att.paid_hours} | status={att.status}"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING('\n--- DRY RUN: Simulating fixes ---\n'))
        else:
            self.stdout.write('')
            confirm = input('Proceed with fix? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Aborted.'))
                return
            self.stdout.write('')

        fixed = 0
        errors = 0

        for att in attendances:
            try:
                with transaction.atomic():
                    emp_name = att.employee.get_full_name()
                    old_type = att.attendance_type
                    old_paid = att.paid_hours

                    # 1. Create an approved WorkRequest if one doesn't exist
                    work_req, wr_created = WorkRequest.objects.get_or_create(
                        employee=att.employee,
                        date=att.date,
                        defaults={
                            'reason': 'Retroactive: employee worked before WorkRequest feature existed',
                            'status': 'approved',
                            'reviewed_at': timezone.now(),
                        },
                    )
                    if not wr_created and work_req.status != 'approved':
                        work_req.status = 'approved'
                        work_req.reviewed_at = timezone.now()
                        work_req.reason = work_req.reason or 'Retroactive fix'
                        if not dry_run:
                            work_req.save()

                    # 2. Recalculate attendance as a normal working day.
                    #    We call compute_attendance_metrics() which will detect
                    #    the shop_closed schedule — but since we now have an
                    #    approved WorkRequest, we temporarily set the type to
                    #    PENDING so the save() path recalculates everything.
                    #    Then we bypass clean() by calling super().save() directly.
                    att.attendance_type = 'PENDING'
                    att.total_hours = Decimal('0.00')
                    att.break_hours = Decimal('0.00')
                    att.paid_hours = Decimal('0.00')

                    # Recalculate lateness
                    att.calculate_lateness()

                    # Recalculate full metrics (this will re-detect shop_closed
                    # and set SHOP_CLOSED again since HalfDaySchedule still exists).
                    # To avoid that, we call the computation manually and then
                    # override the attendance_type based on actual hours.
                    att.compute_attendance_metrics()

                    # If compute_attendance_metrics set it back to SHOP_CLOSED,
                    # override to the correct type based on worked hours.
                    if att.attendance_type == 'SHOP_CLOSED':
                        paid = att.paid_hours
                        if paid >= Decimal('8.00'):
                            att.attendance_type = 'FULL_DAY'
                            att.paid_hours = Decimal('8.00')
                        elif Decimal('3.50') <= paid <= Decimal('4.50'):
                            att.attendance_type = 'HALF_DAY'
                            att.paid_hours = Decimal('4.00')
                        elif paid >= Decimal('1.00'):
                            att.attendance_type = 'PARTIAL'
                        else:
                            att.attendance_type = 'INVALID'
                            att.status = 'REJECTED'

                    att.status = 'APPROVED'

                    new_type = att.attendance_type
                    new_paid = att.paid_hours

                    if dry_run:
                        wr_label = 'create' if wr_created else 'exists'
                        self.stdout.write(self.style.WARNING(
                            f"  [DRY RUN] ID {att.id}: {emp_name} | {att.date} | "
                            f"{old_type}({old_paid}h) -> {new_type}({new_paid}h) | "
                            f"WorkRequest: {wr_label}"
                        ))
                        # Rollback the transaction in dry-run
                        transaction.set_rollback(True)
                    else:
                        # Save bypassing clean() by using update_fields via super()
                        DailyAttendance.objects.filter(pk=att.pk).update(
                            attendance_type=att.attendance_type,
                            total_hours=att.total_hours,
                            break_hours=att.break_hours,
                            paid_hours=att.paid_hours,
                            is_late=att.is_late,
                            late_minutes=att.late_minutes,
                            late_penalty_amount=att.late_penalty_amount,
                            consecutive_absences=att.consecutive_absences,
                            is_awol=att.is_awol,
                            status=att.status,
                            notes=f"Fixed from SHOP_CLOSED: employee worked this day. Original paid_hours={old_paid}",
                        )
                        self.stdout.write(self.style.SUCCESS(
                            f"  FIXED ID {att.id}: {emp_name} | {att.date} | "
                            f"{old_type}({old_paid}h) -> {new_type}({new_paid}h)"
                        ))

                    fixed += 1

            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(
                    f"  ERROR ID {att.id}: {att.employee.get_full_name()} | {att.date} | {e}"
                ))

        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f"Total processed: {fixed + errors}")
        self.stdout.write(self.style.SUCCESS(f"Fixed: {fixed}"))
        if errors:
            self.stdout.write(self.style.ERROR(f"Errors: {errors}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("(Dry run — no changes were saved)"))
        self.stdout.write(self.style.SUCCESS('=' * 80 + '\n'))
