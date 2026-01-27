from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from datetime import date
from .models import LeaveBalance

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
                'sick_leave_total': 5,
                'emergency_leave_total': 5,
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
                'sick_leave_total': 5,
                'emergency_leave_total': 5,
                'sick_leave_used': 0,
                'emergency_leave_used': 0,
            }
        )
        if created:
            created_count += 1
    
    return created_count
