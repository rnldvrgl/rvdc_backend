"""
Verification script for attendance time entry calculations.

This script checks attendance records for calculation issues without making changes.
It's useful for identifying problematic records before running the fix command.

Usage:
    python rvdc_backend/attendance/verify_attendance_fix.py
"""

import os
import sys
from datetime import datetime, time, timedelta
from decimal import Decimal

import django

# Setup Django environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rvdc_backend.settings')
django.setup()

from django.utils import timezone
from payroll.models import PayrollSettings

from attendance.models import DailyAttendance


def round_decimal(value):
    """Round to 2 decimal places."""
    from decimal import ROUND_HALF_UP
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def check_attendance(attendance):
    """Check a single attendance record for issues."""
    issues = []
    warnings = []
    tolerance = Decimal('0.01')

    # Skip ABSENT and LEAVE types
    if attendance.attendance_type in ['ABSENT', 'LEAVE']:
        return issues, warnings

    # Check 1: Clock times exist
    if not attendance.clock_in:
        issues.append('Missing clock_in time')
        return issues, warnings

    if not attendance.clock_out and attendance.attendance_type not in ['ABSENT', 'LEAVE']:
        issues.append('Missing clock_out time')
        return issues, warnings

    # Check 2: Total hours calculation
    if attendance.clock_in and attendance.clock_out:
        delta = attendance.clock_out - attendance.clock_in
        expected_total = Decimal(delta.total_seconds()) / Decimal(3600)
        expected_total = round_decimal(expected_total)

        if abs(expected_total - attendance.total_hours) > tolerance:
            issues.append(
                f'Total hours mismatch: {expected_total}h (calculated) vs '
                f'{attendance.total_hours}h (stored)'
            )

    # Check 3: Lateness calculation
    try:
        settings = PayrollSettings.objects.first()
        grace_minutes = settings.grace_minutes if settings else 15
        shift_start = settings.shift_start if settings else time(8, 0)
    except Exception:
        grace_minutes = 15
        shift_start = time(8, 0)

    if attendance.clock_in:
        tz = timezone.get_current_timezone()
        clock_in_local = attendance.clock_in
        if not timezone.is_aware(clock_in_local):
            clock_in_local = timezone.make_aware(clock_in_local, tz)

        local_date = clock_in_local.astimezone(tz).date()
        grace_limit = datetime.combine(local_date, shift_start) + timedelta(minutes=grace_minutes)
        grace_limit = timezone.make_aware(grace_limit, tz)

        if clock_in_local > grace_limit:
            late_delta = (clock_in_local - grace_limit).total_seconds() / 60
            expected_late_minutes = int(late_delta)
            expected_penalty = Decimal(str(expected_late_minutes * 2))

            if not attendance.is_late:
                issues.append(f'Should be marked as late ({expected_late_minutes} min)')
            elif attendance.late_minutes != expected_late_minutes:
                issues.append(
                    f'Late minutes mismatch: {expected_late_minutes} (calc) vs '
                    f'{attendance.late_minutes} (stored)'
                )
            elif abs(attendance.late_penalty_amount - expected_penalty) > tolerance:
                issues.append(
                    f'Late penalty mismatch: ₱{expected_penalty} (calc) vs '
                    f'₱{attendance.late_penalty_amount} (stored)'
                )

    # Check 4: Uniform penalties
    expected_uniform_penalty = Decimal('0.00')
    if attendance.missing_uniform_shirt:
        expected_uniform_penalty += Decimal('50.00')
    if attendance.missing_uniform_pants:
        expected_uniform_penalty += Decimal('50.00')
    if attendance.missing_uniform_shoes:
        expected_uniform_penalty += Decimal('50.00')

    if abs(attendance.uniform_penalty_amount - expected_uniform_penalty) > tolerance:
        issues.append(
            f'Uniform penalty mismatch: ₱{expected_uniform_penalty} (calc) vs '
            f'₱{attendance.uniform_penalty_amount} (stored)'
        )

    # Check 5: Paid hours reasonableness
    if attendance.paid_hours < 0:
        issues.append(f'Negative paid hours: {attendance.paid_hours}')
    elif attendance.paid_hours > attendance.total_hours:
        issues.append(
            f'Paid hours ({attendance.paid_hours}) exceeds total hours ({attendance.total_hours})'
        )

    # Check 6: Attendance type validation
    if attendance.total_hours >= Decimal('10.00') and attendance.paid_hours < Decimal('8.00'):
        if attendance.attendance_type != 'FULL_DAY' and not attendance.is_late:
            warnings.append(
                f'Might be FULL_DAY (worked {attendance.total_hours}h) but is {attendance.attendance_type}'
            )

    # Check 7: Break hours reasonableness
    if attendance.break_hours < 0:
        issues.append(f'Negative break hours: {attendance.break_hours}')
    elif attendance.break_hours > attendance.total_hours:
        issues.append(
            f'Break hours ({attendance.break_hours}) exceeds total hours ({attendance.total_hours})'
        )

    # Check 8: Auto-close warning
    if attendance.auto_closed:
        warnings.append(f'Auto-closed attendance (warning count: {attendance.auto_close_warning_count})')

    return issues, warnings


def verify_attendance_records():
    """Verify all attendance records."""
    print("\n" + "=" * 80)
    print("ATTENDANCE TIME ENTRY VERIFICATION")
    print("=" * 80)

    # Get attendance records
    attendances = DailyAttendance.objects.filter(
        is_deleted=False,
        status__in=['PENDING', 'APPROVED']
    ).exclude(
        attendance_type__in=['ABSENT', 'LEAVE']
    ).order_by('-date', 'employee__first_name')

    total_count = attendances.count()
    print(f"\nChecking {total_count} attendance records...\n")

    passed = 0
    failed = 0
    warned = 0
    all_issues = []
    all_warnings = []

    print("-" * 80)

    for attendance in attendances:
        issues, warnings = check_attendance(attendance)

        if issues:
            failed += 1
            all_issues.extend([
                f"Attendance {attendance.id} ({attendance.employee.get_full_name()} - {attendance.date}): {issue}"
                for issue in issues
            ])
            print(f"\n❌ Attendance {attendance.id} - {attendance.employee.get_full_name()} - {attendance.date}")
            print(f"   Type: {attendance.attendance_type}, Status: {attendance.status}")
            for issue in issues:
                print(f"   ERROR: {issue}")
            if warnings:
                for warning in warnings:
                    print(f"   WARNING: {warning}")
        elif warnings:
            warned += 1
            all_warnings.extend([
                f"Attendance {attendance.id} ({attendance.employee.get_full_name()} - {attendance.date}): {warning}"
                for warning in warnings
            ])
            print(f"\n⚠️  Attendance {attendance.id} - {attendance.employee.get_full_name()} - {attendance.date}")
            for warning in warnings:
                print(f"   WARNING: {warning}")
        else:
            passed += 1

    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    print(f"Total Checked: {total_count}")
    print(f"✅ Passed: {passed}")
    print(f"⚠️  Warnings: {warned}")
    print(f"❌ Failed: {failed}")

    if all_issues:
        print("\n" + "-" * 80)
        print("CRITICAL ISSUES (require fixing):")
        print("-" * 80)
        for issue in all_issues[:20]:  # Show first 20
            print(f"  - {issue}")
        if len(all_issues) > 20:
            print(f"  ... and {len(all_issues) - 20} more issues")

    if all_warnings:
        print("\n" + "-" * 80)
        print("WARNINGS (review recommended):")
        print("-" * 80)
        for warning in all_warnings[:20]:  # Show first 20
            print(f"  - {warning}")
        if len(all_warnings) > 20:
            print(f"  ... and {len(all_warnings) - 20} more warnings")

    if failed > 0:
        print("\n" + "=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)
        print("Issues detected. To fix them, run:")
        print("  python manage.py fix_attendance_time_entries --dry-run")
        print("\nThen apply fixes with:")
        print("  python manage.py fix_attendance_time_entries")
    else:
        print("\n🎉 All attendance records passed verification!")

    print("=" * 80 + "\n")

    return {
        'total': total_count,
        'passed': passed,
        'warned': warned,
        'failed': failed,
        'issues': all_issues,
        'warnings': all_warnings,
    }


if __name__ == '__main__':
    try:
        results = verify_attendance_records()
        sys.exit(0 if results['failed'] == 0 else 1)
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
