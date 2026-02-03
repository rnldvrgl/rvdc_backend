#!/usr/bin/env python
"""
Verification script for payroll deduction fix.
This script checks if deductions are properly reflected in payroll records.

Usage:
    python manage.py shell < payroll/verify_deduction_fix.py

Or in Django shell:
    from payroll.verify_deduction_fix import verify_deductions
    verify_deductions()
"""

import os

import django

# Setup Django if running as standalone script
if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rvdc_backend.settings')
    django.setup()

from decimal import Decimal

from django.db.models import Sum

from payroll.models import (
    GovernmentBenefit,
    WeeklyPayroll,
)


def verify_deductions(payroll_id=None, verbose=True):
    """
    Verify that deductions are properly calculated and stored.

    Args:
        payroll_id: Optional specific payroll ID to check
        verbose: Print detailed information

    Returns:
        dict with verification results
    """
    results = {
        'total_checked': 0,
        'passed': 0,
        'failed': 0,
        'issues': [],
    }

    # Get payrolls to check
    if payroll_id:
        payrolls = WeeklyPayroll.objects.filter(id=payroll_id, is_deleted=False)
    else:
        # Check recent payrolls (last 100)
        payrolls = WeeklyPayroll.objects.filter(is_deleted=False).order_by('-created_at')[:100]

    if verbose:
        print(f"\n{'='*80}")
        print("PAYROLL DEDUCTION VERIFICATION")
        print(f"{'='*80}")
        print(f"Checking {payrolls.count()} payroll record(s)...\n")

    for payroll in payrolls:
        results['total_checked'] += 1
        issues = []

        if verbose:
            print(f"\n{'─'*80}")
            print(f"Payroll ID: {payroll.id}")
            print(f"Employee: {payroll.employee.get_full_name()}")
            print(f"Week: {payroll.week_start} to {payroll.week_end}")
            print(f"Gross Pay: ₱{payroll.gross_pay:,.2f}")

        # Check 1: Verify structured deduction records exist
        deduction_items = payroll.deduction_items.all()
        if verbose:
            print(f"\nStructured Deduction Records: {deduction_items.count()}")

        if deduction_items.count() == 0:
            issues.append("No structured deduction records found")

        # Check 2: Verify government benefits are included
        gov_benefit_items = deduction_items.filter(category__in=['government', 'tax'])
        if verbose:
            print(f"  - Government/Tax: {gov_benefit_items.count()}")

        # Get active government benefits count
        active_gov_benefits = GovernmentBenefit.objects.filter(
            is_active=True,
            effective_start__lte=payroll.week_start,
        ).filter(
            django.db.models.Q(effective_end__isnull=True) |
            django.db.models.Q(effective_end__gte=payroll.week_start)
        ).count()

        if active_gov_benefits > 0 and gov_benefit_items.count() == 0:
            issues.append(f"Expected {active_gov_benefits} government benefits but found 0")

        # Check 3: Verify deductions JSON field is populated
        if not payroll.deductions or len(payroll.deductions) == 0:
            issues.append("Deductions JSON field is empty")

        if verbose and payroll.deductions:
            print("\nDeductions (JSON field):")
            for key, value in payroll.deductions.items():
                print(f"  - {key}: ₱{value:,.2f}")

        # Check 4: Verify total_deductions matches sum of structured records
        structured_total = deduction_items.aggregate(
            total=Sum('employee_share')
        )['total'] or Decimal('0.00')

        json_total = Decimal(str(sum(payroll.deductions.values()))) if payroll.deductions else Decimal('0.00')
        stored_total = Decimal(str(payroll.total_deductions))

        if verbose:
            print("\nDeduction Totals:")
            print(f"  - Structured Records Sum: ₱{structured_total:,.2f}")
            print(f"  - JSON Field Sum: ₱{json_total:,.2f}")
            print(f"  - Stored Total: ₱{stored_total:,.2f}")

        # Allow small rounding differences (0.01)
        tolerance = Decimal('0.01')

        if abs(structured_total - stored_total) > tolerance:
            issues.append(
                f"Total mismatch: Structured (₱{structured_total}) vs Stored (₱{stored_total})"
            )

        if abs(json_total - stored_total) > tolerance:
            issues.append(
                f"JSON mismatch: JSON (₱{json_total}) vs Stored (₱{stored_total})"
            )

        # Check 5: Verify net_pay calculation
        calculated_net_pay = payroll.gross_pay - payroll.total_deductions
        stored_net_pay = Decimal(str(payroll.net_pay))

        if abs(calculated_net_pay - stored_net_pay) > tolerance:
            issues.append(
                f"Net pay mismatch: Calculated (₱{calculated_net_pay}) vs Stored (₱{stored_net_pay})"
            )

        if verbose:
            print(f"  - Net Pay: ₱{stored_net_pay:,.2f}")

        # Check 6: List deduction breakdown
        if verbose and deduction_items.count() > 0:
            print("\nDeduction Breakdown:")
            for item in deduction_items:
                print(f"  - [{item.category}] {item.name}: ₱{item.employee_share:,.2f}")
                if item.employer_share > 0:
                    print(f"    (Employer share: ₱{item.employer_share:,.2f})")

        # Record results
        if issues:
            results['failed'] += 1
            results['issues'].extend([f"Payroll {payroll.id}: {issue}" for issue in issues])
            if verbose:
                print("\n⚠️  ISSUES FOUND:")
                for issue in issues:
                    print(f"    - {issue}")
        else:
            results['passed'] += 1
            if verbose:
                print("\n✅ PASSED - All checks OK")

    # Print summary
    if verbose:
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        print(f"Total Checked: {results['total_checked']}")
        print(f"Passed: {results['passed']} ✅")
        print(f"Failed: {results['failed']} ❌")

        if results['issues']:
            print("\nIssues Found:")
            for issue in results['issues']:
                print(f"  - {issue}")
        else:
            print("\n🎉 All payroll records passed verification!")
        print(f"{'='*80}\n")

    return results


def fix_existing_payrolls(payroll_ids=None, dry_run=True):
    """
    Fix existing payroll records by regenerating deduction records.

    Args:
        payroll_ids: List of specific payroll IDs to fix, or None for all draft payrolls
        dry_run: If True, only show what would be fixed without making changes

    Returns:
        dict with fix results
    """
    results = {
        'total_processed': 0,
        'fixed': 0,
        'skipped': 0,
        'errors': [],
    }

    # Get payrolls to fix
    if payroll_ids:
        payrolls = WeeklyPayroll.objects.filter(id__in=payroll_ids, is_deleted=False)
    else:
        # Fix draft payrolls only by default
        payrolls = WeeklyPayroll.objects.filter(status='draft', is_deleted=False)

    print(f"\n{'='*80}")
    print("PAYROLL DEDUCTION FIX")
    print(f"{'='*80}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will update records)'}")
    print(f"Found {payrolls.count()} payroll record(s) to process...\n")

    for payroll in payrolls:
        results['total_processed'] += 1

        try:
            old_total = payroll.total_deductions
            old_deductions_count = payroll.deduction_items.count()

            print(f"\nPayroll {payroll.id} ({payroll.employee.get_full_name()}):")
            print(f"  Current: {old_deductions_count} items, ₱{old_total:,.2f} total")

            if not dry_run:
                # Regenerate deduction records (this will update the fields)
                payroll.create_deduction_records()
                payroll.refresh_from_db()

                new_total = payroll.total_deductions
                new_deductions_count = payroll.deduction_items.count()

                print(f"  Updated: {new_deductions_count} items, ₱{new_total:,.2f} total")
                print(f"  Change: {new_deductions_count - old_deductions_count:+d} items, "
                      f"₱{new_total - old_total:+,.2f}")

                results['fixed'] += 1
            else:
                print("  Would regenerate deduction records")
                results['fixed'] += 1

        except Exception as e:
            error_msg = f"Payroll {payroll.id}: {str(e)}"
            results['errors'].append(error_msg)
            print(f"  ❌ ERROR: {e}")

    # Print summary
    print(f"\n{'='*80}")
    print("FIX SUMMARY")
    print(f"{'='*80}")
    print(f"Total Processed: {results['total_processed']}")
    print(f"Fixed: {results['fixed']} ✅")
    print(f"Skipped: {results['skipped']}")
    print(f"Errors: {len(results['errors'])} ❌")

    if results['errors']:
        print("\nErrors:")
        for error in results['errors']:
            print(f"  - {error}")

    if dry_run:
        print("\n⚠️  This was a DRY RUN. No changes were made.")
        print("To apply fixes, run: fix_existing_payrolls(dry_run=False)")
    else:
        print(f"\n✅ Fix applied to {results['fixed']} payroll record(s).")

    print(f"{'='*80}\n")

    return results


if __name__ == "__main__":
    # Run verification
    verify_deductions(verbose=True)

    # Optionally run fix (uncomment to enable)
    # fix_existing_payrolls(dry_run=True)
