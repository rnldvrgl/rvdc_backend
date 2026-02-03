from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from users.models import CustomUser
from datetime import datetime


@receiver(pre_save, sender=CustomUser)
def validate_single_manager_clerk(sender, instance, **kwargs):
    """
    Ensure only one manager and one clerk exist in the database.
    """
    # Skip validation if user is being soft-deleted
    if instance.is_deleted:
        return
    
    # Check for manager uniqueness
    if instance.role == "manager":
        existing_managers = CustomUser.objects.filter(
            role="manager",
            is_deleted=False
        ).exclude(pk=instance.pk)
        
        if existing_managers.exists():
            raise ValidationError(
                "Only one manager is allowed in the system. "
                f"A manager already exists: {existing_managers.first().get_full_name()}"
            )
    
    # Check for clerk uniqueness
    if instance.role == "clerk":
        existing_clerks = CustomUser.objects.filter(
            role="clerk",
            is_deleted=False
        ).exclude(pk=instance.pk)
        
        if existing_clerks.exists():
            raise ValidationError(
                "Only one clerk is allowed in the system. "
                f"A clerk already exists: {existing_clerks.first().get_full_name()}"
            )


@receiver(post_save, sender=CustomUser)
def create_leave_balance_for_employee(sender, instance, created, **kwargs):
    """
    Automatically create leave balance for new technicians, managers, and clerks.
    """
    # Only create leave balance for new users with eligible roles
    if created and instance.role in ["technician", "manager", "clerk"]:
        from attendance.models import LeaveBalance
        
        current_year = datetime.now().year
        
        # Check if leave balance already exists for this year
        if not LeaveBalance.objects.filter(
            employee=instance,
            year=current_year
        ).exists():
            LeaveBalance.objects.create(
                employee=instance,
                year=current_year,
                sick_leave_total=5,
                sick_leave_used=0,
                emergency_leave_total=5,
                emergency_leave_used=0
            )
