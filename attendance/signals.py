from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import LeaveBalance, OvertimeRequest

User = get_user_model()


@receiver(post_save, sender=User)
def create_leave_balance_for_new_employee(sender, instance, created, **kwargs):
    """
    Auto-create leave balance for new employees for the current year.
    """
    if created and not instance.is_deleted:
        current_year = date.today().year

        # Create leave balance for current year
        LeaveBalance.objects.get_or_create(
            employee=instance,
            year=current_year,
            defaults={
                'sick_leave_total': 7,
                'emergency_leave_total': 3,
                'sick_leave_used': 0,
                'emergency_leave_used': 0,
            }
        )


def create_leave_balances_for_new_year(year: int):
    """
    Utility function to create leave balances for all active employees for a new year.
    Should be called at the beginning of each year (e.g., via scheduled task on Jan 1).

    Args:
        year: The year to create balances for (e.g., 2026)
    """
    User = get_user_model()
    active_employees = User.objects.filter(is_deleted=False, is_active=True)

    created_count = 0
    for employee in active_employees:
        _, created = LeaveBalance.objects.get_or_create(
            employee=employee,
            year=year,
            defaults={
                'sick_leave_total': 7,
                'emergency_leave_total': 3,
                'sick_leave_used': 0,
                'emergency_leave_used': 0,
            }
        )
        if created:
            created_count += 1

    return created_count


@receiver(pre_save, sender=OvertimeRequest)
def validate_overtime_approval_against_payroll_status(sender, instance, **kwargs):
    """
    Validate overtime approval against existing payroll status.

    Rules:
    - If approving overtime (approved=True) and there are existing payrolls for that week:
      - DRAFT payrolls → OK, will be auto-updated after save
      - APPROVED/PAID/RECEIVED payrolls → BLOCK with error message

    This ensures data integrity by preventing overtime approval when payroll
    is already finalized.
    """
    # Only validate when approving (not when rejecting or creating)
    if not instance.approved:
        return

    # Skip validation if this is already approved (updating other fields)
    if instance.pk:
        try:
            old_instance = OvertimeRequest.objects.get(pk=instance.pk)
            if old_instance.approved:
                # Already approved, skip validation
                return
        except OvertimeRequest.DoesNotExist:
            pass

    # Import here to avoid circular imports
    from payroll.models import WeeklyPayroll

    overtime_date = instance.date

    # Find payrolls that contain this overtime date
    payrolls = WeeklyPayroll.objects.filter(
        employee=instance.employee,
        is_deleted=False,
        week_start__lte=overtime_date,
    )

    # Check if any non-draft payrolls exist for this week
    non_draft_payrolls = []
    for payroll in payrolls:
        if overtime_date <= payroll.week_end:
            if payroll.status != 'draft':
                non_draft_payrolls.append(payroll)

    if non_draft_payrolls:
        # Block the approval
        payroll = non_draft_payrolls[0]
        raise ValidationError(
            f"Cannot approve overtime request. A payroll for week {payroll.week_start} "
            f"to {payroll.week_end} already exists with status '{payroll.status}'. "
            f"Please set the payroll back to 'draft' status before approving overtime, "
            f"or reject this overtime request."
        )


@receiver(post_save, sender=OvertimeRequest)
def update_draft_payrolls_on_overtime_approval(sender, instance, created, **kwargs):
    """
    Auto-update draft payrolls when an overtime request is approved.

    This signal triggers after an OvertimeRequest is approved to automatically
    recompute any draft payrolls that fall within the overtime date range.

    Only affects payrolls with status='draft'. Non-draft payrolls are protected
    by the pre_save signal above which blocks the approval.
    """
    # Only process if overtime was approved
    if not instance.approved:
        return

    # Import here to avoid circular imports
    from payroll.models import WeeklyPayroll

    overtime_date = instance.date

    # Get all draft payrolls for this employee that contain this overtime date
    draft_payrolls = WeeklyPayroll.objects.filter(
        employee=instance.employee,
        status='draft',
        is_deleted=False,
        week_start__lte=overtime_date,
    )

    # Filter by week_end using Python since it's a property
    updated_count = 0
    for payroll in draft_payrolls:
        if overtime_date <= payroll.week_end:
            try:
                # Recompute the payroll from daily attendance (includes overtime)
                payroll.compute_from_daily_attendance()
                payroll.save(update_fields=[
                    'regular_hours',
                    'overtime_hours',
                    'night_diff_hours',
                    'approved_ot_hours',
                    'approved_ot_pay',
                    'allowances',
                    'additional_earnings_total',
                    'holiday_pay_regular',
                    'holiday_pay_special',
                    'holiday_pay_total',
                    'gross_pay',
                    'deductions',
                    'total_deductions',
                    'net_pay',
                    'updated_at',
                ])
                updated_count += 1
            except Exception as e:
                # Log error but don't fail the approval
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"Failed to auto-update draft payroll {payroll.id} after overtime approval: {e}"
                )

    # Log successful updates
    if updated_count > 0:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"Auto-updated {updated_count} draft payroll(s) after approving overtime "
            f"request {instance.id} for employee {instance.employee_id}"
        )
