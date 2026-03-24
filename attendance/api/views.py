from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from attendance.api.serializers import (
    ApproveAttendanceSerializer,
    ApproveLeaveSerializer,
    ClockInSerializer,
    ClockOutSerializer,
    DailyAttendanceSerializer,
    HalfDayScheduleSerializer,
    LeaveBalanceSerializer,
    LeaveRequestSerializer,
    OffenseSerializer,
    OffenseStatisticsSerializer,
    OvertimeRequestApproveSerializer,
    OvertimeRequestSerializer,
    RejectAttendanceSerializer,
    RejectLeaveSerializer,
    ValidateLeaveBalanceSerializer,
    WorkRequestSerializer,
)
from attendance.models import (
    DailyAttendance,
    HalfDaySchedule,
    LeaveBalance,
    LeaveRequest,
    Offense,
    OvertimeRequest,
    WorkRequest,
)
from utils.soft_delete import SoftDeleteViewSetMixin


class IsAdminOnly(IsAuthenticated):
    """Permission class for admin role only."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.role == 'admin'


class DailyAttendanceViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for daily attendance management.

    Permissions:
    - Admin/Manager: Full access (clock-in/out, approve, view all)
    - Clerk/Technician: Read-only access to their own attendance
    """
    serializer_class = DailyAttendanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = DailyAttendance.objects.filter(is_deleted=False)

        # Only admin can see all attendance
        if user.role == 'admin':
            # Optional filters
            employee_id = self.request.query_params.get('employee_id')
            status_filter = self.request.query_params.get('status')
            date_from = self.request.query_params.get('date_from')
            date_to = self.request.query_params.get('date_to')

            if employee_id:
                queryset = queryset.filter(employee_id=employee_id)
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            if date_from:
                queryset = queryset.filter(date__gte=date_from)
            if date_to:
                queryset = queryset.filter(date__lte=date_to)
        else:
            # All non-admin users can only see their own attendance
            queryset = queryset.filter(employee=user)

        return queryset.select_related('employee', 'approved_by').order_by('-date')

    def create(self, request, *args, **kwargs):
        """Only admin can create attendance records."""
        if request.user.role != 'admin':
            return Response(
                {'detail': 'Only admin can create attendance records.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """Only admin can update attendance records."""
        if request.user.role != 'admin':
            return Response(
                {'detail': 'Only admin can update attendance records.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Soft delete: Only admin can delete."""
        if request.user.role != 'admin':
            return Response(
                {'detail': 'Only admin can delete attendance records.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def current_status(self, request):
        """Get current attendance status including suspension check"""
        from attendance.models import Offense

        attendance = (
            DailyAttendance.objects
            .filter(
                employee=request.user,
                date=timezone.localdate(),
                is_deleted=False
            )
            .first()
        )

        # Check if employee is currently suspended
        is_suspended = Offense.is_employee_suspended(request.user)
        suspension_info = None

        if is_suspended:
            today = timezone.localdate()
            suspension = Offense.objects.filter(
                employee=request.user,
                severity_level='SUSPENSION',
                suspension_start_date__lte=today,
                suspension_end_date__gte=today,
                is_deleted=False,
            ).first()

            if suspension:
                suspension_info = {
                    'is_suspended': True,
                    'suspension_start_date': suspension.suspension_start_date,
                    'suspension_end_date': suspension.suspension_end_date,
                    'offense_type': suspension.get_offense_type_display(),
                }

        if attendance is None:
            response_data = {
                'attendance': None,
                'is_suspended': is_suspended,
                'suspension_info': suspension_info,
                'work_request': self._get_today_work_request(request.user),
            }
            return Response(response_data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(attendance)
        response_data = {
            'attendance': serializer.data,
            'is_suspended': is_suspended,
            'suspension_info': suspension_info,
            'work_request': self._get_today_work_request(request.user),
        }
        return Response(response_data, status=status.HTTP_200_OK)

    def _get_today_work_request(self, user):
        """Get the user's latest work request for today."""
        wr = WorkRequest.objects.filter(
            employee=user,
            date=timezone.localdate(),
        ).order_by('-created_at').first()
        if wr:
            return WorkRequestSerializer(wr).data
        return None

    @action(detail=False, methods=['post'])
    def clock_in(self, request):
        """
        Clock in an employee.

        Required fields:
        - employee_id: ID of the employee
        - date: Date of attendance (YYYY-MM-DD)
        - clock_in: Clock-in datetime
        """
        serializer = ClockInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee_id = serializer.validated_data['employee_id']
        attendance_date = serializer.validated_data['date']
        clock_in_time = serializer.validated_data['clock_in']
        notes = serializer.validated_data.get('notes', '')

        # Check if employee is currently suspended
        from users.models import CustomUser

        from attendance.models import Offense

        try:
            employee = CustomUser.objects.get(id=employee_id)
            if Offense.is_employee_suspended(employee):
                # Get suspension details for error message
                from django.utils import timezone
                today = timezone.now().date()
                suspension = Offense.objects.filter(
                    employee=employee,
                    severity_level='SUSPENSION',
                    suspension_start_date__lte=today,
                    suspension_end_date__gte=today,
                    is_deleted=False,
                ).first()

                if suspension:
                    return Response(
                        {'detail': f'Employee is currently suspended until {suspension.suspension_end_date}. Cannot clock in.'},
                        status=status.HTTP_403_FORBIDDEN
                    )
        except CustomUser.DoesNotExist:
            pass

        # Check if attendance already exists for this employee on this date
        existing = DailyAttendance.objects.filter(
            employee_id=employee_id,
            date=attendance_date,
            is_deleted=False
        ).first()

        if existing:
            # Allow clock-in if the existing record is from a half-day leave
            half_day_leave = LeaveRequest.objects.filter(
                employee_id=employee_id,
                status='APPROVED',
                is_half_day=True,
                shift_period__in=['AM', 'PM'],
            ).filter(
                models.Q(date=attendance_date) |
                models.Q(start_date__lte=attendance_date, end_date__gte=attendance_date)
            ).first()

            if existing.attendance_type == 'LEAVE' and half_day_leave and not existing.clock_in:
                existing.clock_in = clock_in_time
                existing.attendance_type = 'PENDING'
                existing.status = 'PENDING'
                if notes:
                    existing.notes = f"{existing.notes}\n{notes}" if existing.notes else notes
                existing.save(update_fields=['clock_in', 'attendance_type', 'status', 'notes', 'updated_at'])
                return Response(
                    DailyAttendanceSerializer(existing).data,
                    status=status.HTTP_200_OK
                )

            return Response(
                {'detail': f'Attendance already exists for this employee on {attendance_date}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create new attendance record
        attendance = DailyAttendance.objects.create(
            employee_id=employee_id,
            date=attendance_date,
            clock_in=clock_in_time,
            notes=notes,
            status='PENDING',
        )

        return Response(
            DailyAttendanceSerializer(attendance).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=['post'])
    def clock_out(self, request):
        """
        Clock out an employee.

        Required fields:
        - attendance_id: ID of the attendance record
        - clock_out: Clock-out datetime
        """
        serializer = ClockOutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        attendance_id = serializer.validated_data['attendance_id']
        clock_out_time = serializer.validated_data['clock_out']
        notes = serializer.validated_data.get('notes', '')

        attendance = get_object_or_404(DailyAttendance, id=attendance_id, is_deleted=False)

        if attendance.clock_out:
            return Response(
                {'detail': 'Employee already clocked out for this attendance.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update clock-out time (save() will auto-compute metrics)
        attendance.clock_out = clock_out_time
        if notes:
            attendance.notes = f"{attendance.notes}\n{notes}".strip()
        attendance.save()

        return Response(
            DailyAttendanceSerializer(attendance).data,
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOnly])
    def approve(self, request):
        """
        Approve one or more attendance records.

        Required fields:
        - attendance_ids: List of attendance IDs to approve
        """
        serializer = ApproveAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        attendance_ids = serializer.validated_data['attendance_ids']
        attendances = DailyAttendance.objects.filter(
            id__in=attendance_ids,
            is_deleted=False,
            status='PENDING'
        )

        approved_count = 0
        approved_attendances = []
        for attendance in attendances:
            attendance.approve(request.user)
            approved_count += 1
            approved_attendances.append(attendance)

        # Notify employees
        from notifications.models import Notification, NotificationType
        for att in approved_attendances:
            Notification.objects.create(
                user=att.employee,
                type=NotificationType.ATTENDANCE_APPROVED,
                title="Attendance Approved",
                message=f"Your attendance for {att.date} has been approved.",
                data={"attendance_id": att.id, "date": str(att.date)},
            )

        return Response(
            {
                'detail': f'{approved_count} attendance record(s) approved.',
                'approved_count': approved_count,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOnly])
    def reject(self, request):
        """
        Reject one or more attendance records.

        Required fields:
        - attendance_ids: List of attendance IDs to reject
        - reason: Optional rejection reason
        """
        serializer = RejectAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        attendance_ids = serializer.validated_data['attendance_ids']
        reason = serializer.validated_data.get('reason', '')

        attendances = DailyAttendance.objects.filter(
            id__in=attendance_ids,
            is_deleted=False,
            status='PENDING'
        )

        rejected_count = 0
        rejected_attendances = []
        for attendance in attendances:
            attendance.reject(request.user, reason=reason)
            rejected_count += 1
            rejected_attendances.append(attendance)

        # Notify employees
        from notifications.models import Notification, NotificationType
        for att in rejected_attendances:
            Notification.objects.create(
                user=att.employee,
                type=NotificationType.ATTENDANCE_REJECTED,
                title="Attendance Rejected",
                message=f"Your attendance for {att.date} has been rejected."
                        + (f" Reason: {reason}" if reason else ""),
                data={"attendance_id": att.id, "date": str(att.date)},
            )

        return Response(
            {
                'detail': f'{rejected_count} attendance record(s) rejected.',
                'rejected_count': rejected_count,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['patch'], permission_classes=[IsAdminOnly])
    def update_uniform_penalties(self, request, pk=None):
        """
        Update uniform penalty flags for an attendance record.

        Required fields (all boolean):
        - missing_uniform_shirt
        - missing_uniform_pants
        - missing_uniform_shoes
        """
        attendance = self.get_object()

        # Only update uniform penalties for PENDING or APPROVED records
        if attendance.status not in ['PENDING', 'APPROVED']:
            return Response(
                {'detail': 'Can only update uniform penalties for pending or approved attendance.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update uniform flags
        attendance.missing_uniform_shirt = request.data.get('missing_uniform_shirt', False)
        attendance.missing_uniform_pants = request.data.get('missing_uniform_pants', False)
        attendance.missing_uniform_shoes = request.data.get('missing_uniform_shoes', False)

        # Save will automatically recalculate uniform_penalty_amount
        attendance.save()

        return Response(
            DailyAttendanceSerializer(attendance).data,
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOnly])
    def mark_absent(self, request):
        """
        Manually mark one or more employees as absent for a given date.
        
        Required fields:
        - employee_ids: List of employee IDs to mark absent
        - date: Date to mark absent for (YYYY-MM-DD)
        
        Optional fields:
        - reason: 'shop_closed' to mark as Shop Closed (no AWOL counting)
        """
        employee_ids = request.data.get('employee_ids', [])
        target_date = request.data.get('date')
        reason = request.data.get('reason', '')
        is_shop_closed = reason == 'shop_closed'

        if not employee_ids:
            return Response(
                {'detail': 'employee_ids is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not target_date:
            return Response(
                {'detail': 'date is required (YYYY-MM-DD).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from datetime import datetime as dt
        try:
            parsed_date = dt.strptime(target_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return Response(
                {'detail': 'Invalid date format. Use YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from users.models import CustomUser
        employees = CustomUser.objects.filter(id__in=employee_ids, is_active=True, is_deleted=False)

        if not employees.exists():
            return Response(
                {'detail': 'No valid employees found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        marked_count = 0
        skipped = []
        for employee in employees:
            attendance, created = DailyAttendance.objects.get_or_create(
                employee=employee,
                date=parsed_date,
                defaults={'attendance_type': 'PENDING'},
            )

            # Skip if already marked as ABSENT, LEAVE, or SHOP_CLOSED
            if attendance.attendance_type in ['ABSENT', 'LEAVE', 'SHOP_CLOSED']:
                skipped.append({
                    'employee_id': employee.id,
                    'name': employee.get_full_name(),
                    'reason': f'Already marked as {attendance.get_attendance_type_display()}',
                })
                continue

            # Skip if employee already clocked in (has actual attendance)
            if attendance.clock_in:
                skipped.append({
                    'employee_id': employee.id,
                    'name': employee.get_full_name(),
                    'reason': 'Employee has already clocked in',
                })
                continue

            if is_shop_closed:
                from decimal import Decimal
                attendance.attendance_type = 'SHOP_CLOSED'
                attendance.consecutive_absences = 0
                attendance.is_awol = False
                attendance.clock_in = None
                attendance.clock_out = None
                attendance.total_hours = Decimal('0.00')
                attendance.paid_hours = Decimal('0.00')
                attendance.break_hours = Decimal('0.00')
                attendance.is_late = False
                attendance.late_minutes = 0
                attendance.late_penalty_amount = Decimal('0.00')
                attendance.status = 'APPROVED'
            else:
                attendance.mark_absent()
            attendance.save()
            marked_count += 1

        action_label = 'shop closed' if is_shop_closed else 'absent'
        return Response(
            {
                'detail': f'{marked_count} employee(s) marked as {action_label} for {target_date}.',
                'marked_count': marked_count,
                'skipped': skipped,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def pending_approvals(self, request):
        """Get all pending attendance records (admin only)."""
        if request.user.role != "admin":
            return Response(
                {"detail": "Only admin can view pending approvals."},
                status=status.HTTP_403_FORBIDDEN,
            )

        employee_id = request.query_params.get("employee_id")
        search = request.query_params.get("search", "").strip()

        queryset = (
            DailyAttendance.objects.filter(
                status="PENDING",
                is_deleted=False,
            )
            .select_related("employee", "approved_by")
            .order_by("-date")
        )

        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)

        if search:
            queryset = queryset.filter(
                models.Q(employee__first_name__icontains=search)
                | models.Q(employee__last_name__icontains=search)
                | models.Q(notes__icontains=search)
            )

        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)


class LeaveBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing leave balances.

    Permissions:
    - Admin/Manager: View all leave balances
    - Clerk/Technician: View their own leave balance only
    """
    serializer_class = LeaveBalanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = LeaveBalance.objects.all()

        # Only admin can see all balances
        if user.role == 'admin':
            employee_id = self.request.query_params.get('employee_id')
            year = self.request.query_params.get('year')

            if employee_id:
                queryset = queryset.filter(employee_id=employee_id)
            if year:
                queryset = queryset.filter(year=year)
        else:
            # Employees can only see their own balance
            queryset = queryset.filter(employee=user)

        return queryset.select_related('employee').order_by('-year')

    @action(detail=False, methods=['get'])
    def my_balance(self, request):
        """Get current user's leave balance for current year."""
        current_year = date.today().year
        balance, _ = LeaveBalance.objects.get_or_create(
            employee=request.user,
            year=current_year,
            defaults={
                'sick_leave_total': 5,
                'emergency_leave_total': 5,
            }
        )

        serializer = self.get_serializer(balance)
        return Response(serializer.data)


class LeaveRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for leave request management.

    Permissions:
    - All authenticated users can create leave requests
    - Admin/Manager: Can approve/reject and view all requests
    - Clerk/Technician: Can only view their own requests
    """
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params

        queryset = LeaveRequest.objects.all()

        status_filter = params.get("status")
        date = params.get("date")

        # Non-admins can only see their own requests
        if user.role != "admin":
            queryset = queryset.filter(employee=user)
        else:
            # Admin-only filters
            employee_id = params.get("employee_id")
            leave_type = params.get("leave_type")

            if employee_id:
                queryset = queryset.filter(employee_id=employee_id)

            if leave_type:
                queryset = queryset.filter(leave_type=leave_type)

        # Shared filters
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if date:
            queryset = queryset.filter(date=date)

        return (
            queryset
            .select_related("employee", "approved_by")
            .order_by("-date")
        )

    def create(self, request, *args, **kwargs):
        """Override create to handle validation and return proper Response objects."""
        from datetime import timedelta
        from decimal import Decimal

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # Return validation errors in expected format
            errors = serializer.errors
            if 'detail' in errors:
                return Response(errors, status=status.HTTP_400_BAD_REQUEST)
            # Convert field errors to detail format
            first_error = next(iter(errors.values()))[0]
            return Response(
                {'detail': str(first_error)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get validated data
        validated_data = serializer.validated_data

        # Set employee for non-admin users
        if request.user.role not in ['admin']:
            validated_data['employee'] = request.user

        employee = validated_data.get('employee')
        leave_type = validated_data.get('leave_type')
        is_half_day = validated_data.get('is_half_day', False)

        # Handle date range (start_date / end_date)
        start_date = validated_data.get('start_date')
        end_date = validated_data.get('end_date')

        # Backward compatibility: if start_date/end_date not provided, use date
        if not start_date:
            start_date = validated_data.get('date')
            end_date = start_date
        
        if not start_date:
            return Response(
                {'detail': 'Start date is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not end_date:
            end_date = start_date

        if end_date < start_date:
            return Response(
                {'detail': 'End date must be on or after start date.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate total days
        delta_days = (end_date - start_date).days + 1

        if is_half_day and delta_days > 1:
            return Response(
                {'detail': 'Half-day leave is only allowed for single-day requests.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        days_count = Decimal('0.5') if is_half_day else Decimal(str(delta_days))

        # Set the legacy date field to start_date
        validated_data['date'] = start_date
        validated_data['start_date'] = start_date
        validated_data['end_date'] = end_date

        # Check for duplicate/overlapping leave requests for each date in range
        current_date = start_date
        while current_date <= end_date:
            existing = LeaveRequest.objects.filter(
                employee=employee,
                status__in=['PENDING', 'APPROVED']
            ).filter(
                # Check overlap: existing leave's date range overlaps with current_date
                models.Q(date=current_date) |
                (models.Q(start_date__lte=current_date) & models.Q(end_date__gte=current_date))
            ).exists()

            if existing:
                return Response(
                    {'detail': f'Leave request already exists for {current_date}.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if attendance already exists
            attendance_exists = DailyAttendance.objects.filter(
                employee=employee,
                date=current_date,
            ).exclude(
                clock_in__isnull=True
            ).exists()

            if attendance_exists:
                return Response(
                    {'detail': f'Attendance already recorded for {current_date}, cannot request leave.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            current_date += timedelta(days=1)

        # Check leave balance
        year = start_date.year
        leave_balance, _ = LeaveBalance.objects.get_or_create(
            employee=employee,
            year=year,
            defaults={
                'sick_leave_total': 5,
                'emergency_leave_total': 5,
            }
        )

        if not leave_balance.can_take_leave(leave_type, days_count):
            remaining = leave_balance.get_remaining_balance(leave_type)
            return Response(
                {'detail': f'Insufficient {leave_type.lower()} leave balance. Requesting {days_count} day(s) but only {remaining} remaining.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Deduct balance (skip for SPECIAL leave - no balance consumed)
        if leave_type == 'SICK':
            leave_balance.sick_leave_used += days_count
            leave_balance.save()
        elif leave_type == 'EMERGENCY':
            leave_balance.emergency_leave_used += days_count
            leave_balance.save()

        # Create the leave request
        leave_request = LeaveRequest.objects.create(**validated_data)

        # Return success response
        response_serializer = self.get_serializer(leave_request)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED
        )

    def perform_create(self, serializer):
        """Set the employee to the current user if not specified."""
        if self.request.user.role in ['admin']:
            # Admin can create for any employee
            serializer.save()
        else:
            # Regular employees can only create for themselves
            serializer.save(employee=self.request.user)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOnly])
    def approve(self, request):
        """
        Approve one or more leave requests.

        Required fields:
        - leave_request_ids: List of leave request IDs to approve
        """
        from django.core.exceptions import ValidationError

        serializer = ApproveLeaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        leave_request_ids = serializer.validated_data['leave_request_ids']
        leave_requests = LeaveRequest.objects.filter(
            id__in=leave_request_ids,
            status='PENDING'
        )

        approved_count = 0
        errors = []

        approved_requests = []
        for leave_request in leave_requests:
            try:
                leave_request.approve(request.user)
                approved_count += 1
                approved_requests.append(leave_request)
            except ValidationError as e:
                errors.append({
                    'leave_request_id': leave_request.id,
                    'error': str(e)
                })
            except Exception as e:
                errors.append({
                    'leave_request_id': leave_request.id,
                    'error': str(e)
                })

        # Notify employees
        from notifications.models import Notification, NotificationType
        for lr in approved_requests:
            Notification.objects.create(
                user=lr.employee,
                type=NotificationType.LEAVE_REQUEST_APPROVED,
                title="Leave Request Approved",
                message=f"Your {lr.get_leave_type_display()} leave request for {lr.start_date or lr.date}"
                        + (f" to {lr.end_date}" if lr.end_date and lr.end_date != (lr.start_date or lr.date) else "")
                        + " has been approved.",
                data={"leave_request_id": lr.id, "date": str(lr.start_date or lr.date)},
            )

        if errors:
            return Response(
                {
                    'detail': f'{approved_count} leave request(s) approved, {len(errors)} failed.',
                    'approved_count': approved_count,
                    'errors': errors
                },
                status=status.HTTP_400_BAD_REQUEST if approved_count == 0 else status.HTTP_200_OK
            )

        return Response(
            {
                'detail': f'{approved_count} leave request(s) approved successfully.',
                'approved_count': approved_count,
            },
            status=status.HTTP_200_OK
        )


    @action(detail=False, methods=['post'], permission_classes=[IsAdminOnly])
    def reject(self, request):
        """
        Reject one or more leave requests.

        Required fields:
        - leave_request_ids: List of leave request IDs to reject
        - reason: Optional rejection reason
        """
        from django.core.exceptions import ValidationError

        serializer = RejectLeaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        leave_request_ids = serializer.validated_data['leave_request_ids']
        reason = serializer.validated_data.get('reason', '')

        leave_requests = LeaveRequest.objects.filter(
            id__in=leave_request_ids,
            status='PENDING'
        )

        rejected_count = 0
        errors = []
        rejected_requests = []

        for leave_request in leave_requests:
            try:
                leave_request.reject(request.user, reason=reason)
                rejected_count += 1
                rejected_requests.append(leave_request)
            except ValidationError as e:
                errors.append({
                    'leave_request_id': leave_request.id,
                    'error': str(e)
                })
            except Exception as e:
                errors.append({
                    'leave_request_id': leave_request.id,
                    'error': str(e)
                })

        # Notify employees
        from notifications.models import Notification, NotificationType
        for lr in rejected_requests:
            Notification.objects.create(
                user=lr.employee,
                type=NotificationType.LEAVE_REQUEST_REJECTED,
                title="Leave Request Rejected",
                message=f"Your {lr.get_leave_type_display()} leave request for {lr.start_date or lr.date}"
                        + (f" to {lr.end_date}" if lr.end_date and lr.end_date != (lr.start_date or lr.date) else "")
                        + " has been rejected."
                        + (f" Reason: {reason}" if reason else ""),
                data={"leave_request_id": lr.id, "date": str(lr.start_date or lr.date)},
            )

        if errors:
            return Response(
                {
                    'detail': f'{rejected_count} leave request(s) rejected, {len(errors)} failed.',
                    'rejected_count': rejected_count,
                    'errors': errors
                },
                status=status.HTTP_400_BAD_REQUEST if rejected_count == 0 else status.HTTP_200_OK
            )

        return Response(
            {
                'detail': f'{rejected_count} leave request(s) rejected successfully.',
                'rejected_count': rejected_count,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["get"])
    def pending_approvals(self, request):
        """Get all pending attendance records (admin only)."""
        if request.user.role not in ["admin"]:
            return Response(
                {"detail": "Only admin can view pending approvals."},
                status=status.HTTP_403_FORBIDDEN,
            )

        employee_id = request.query_params.get("employee_id")

        queryset = (
            LeaveRequest.objects.filter(
                status="PENDING",
            )
            .select_related("employee", "approved_by")
            .order_by("-date")
        )

        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)

        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a pending or approved leave request (restore balance)."""
        from django.core.exceptions import ValidationError

        leave_request = self.get_object()

        # Only the employee or admin can cancel
        if leave_request.employee != request.user and request.user.role not in ['admin']:
            return Response(
                {'detail': 'You do not have permission to cancel this leave request.'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            leave_request.cancel()
            return Response(
                {'detail': 'Leave request cancelled successfully.'},
                status=status.HTTP_200_OK
            )
        except ValidationError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'])
    def validate_leave_balance(self, request):
        """
        Validate leave balance before submitting a leave request.
        Returns remaining balance and whether the request can be fulfilled.
        
        Required fields:
        - leave_type: 'SICK' or 'EMERGENCY'
        - start_date: Start date (YYYY-MM-DD)
        - end_date: End date (YYYY-MM-DD)
        - is_half_day: boolean (optional, default false)
        """
        from datetime import timedelta
        from decimal import Decimal

        serializer = ValidateLeaveBalanceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        leave_type = data['leave_type']
        start_date = data['start_date']
        end_date = data['end_date']
        is_half_day = data.get('is_half_day', False)

        # Determine employee
        employee_id = data.get('employee')
        if request.user.role not in ['admin'] or not employee_id:
            employee = request.user
        else:
            from users.models import CustomUser
            try:
                employee = CustomUser.objects.get(id=employee_id)
            except CustomUser.DoesNotExist:
                return Response(
                    {'detail': 'Employee not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Calculate days
        delta_days = (end_date - start_date).days + 1
        days_count = Decimal('0.5') if is_half_day else Decimal(str(delta_days))

        # Get leave balance
        year = start_date.year
        leave_balance, _ = LeaveBalance.objects.get_or_create(
            employee=employee,
            year=year,
            defaults={
                'sick_leave_total': 5,
                'emergency_leave_total': 5,
            }
        )

        remaining = leave_balance.get_remaining_balance(leave_type)
        can_take = leave_balance.can_take_leave(leave_type, days_count)

        # Check for conflicting dates
        conflicting_dates = []
        current_date = start_date
        while current_date <= end_date:
            existing = LeaveRequest.objects.filter(
                employee=employee,
                status__in=['PENDING', 'APPROVED']
            ).filter(
                models.Q(date=current_date) |
                (models.Q(start_date__lte=current_date) & models.Q(end_date__gte=current_date))
            ).exists()

            if existing:
                conflicting_dates.append(str(current_date))

            attendance_exists = DailyAttendance.objects.filter(
                employee=employee,
                date=current_date,
            ).exclude(
                clock_in__isnull=True
            ).exists()

            if attendance_exists:
                conflicting_dates.append(f'{current_date} (attendance recorded)')

            current_date += timedelta(days=1)

        return Response({
            'valid': can_take and len(conflicting_dates) == 0,
            'days_requested': float(days_count),
            'remaining_balance': float(remaining),
            'has_sufficient_balance': can_take,
            'conflicting_dates': conflicting_dates,
            'leave_type': leave_type,
        })


class OffenseViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for offense management.

    Permissions:
    - Admin/Manager: Full access (create, update, delete, view all)
    - Clerk/Technician: Read-only access to their own offenses

    Endpoints:
    - GET /api/offenses/ - List all offenses (admin) or user's offenses (employee)
    - POST /api/offenses/ - Create offense (admin/manager only)
    - GET /api/offenses/{id}/ - Get offense detail
    - PUT/PATCH /api/offenses/{id}/ - Update offense (admin/manager only)
    - DELETE /api/offenses/{id}/ - Delete offense (admin/manager only)
    - GET /api/offenses/statistics/ - Get offense statistics per employee
    - GET /api/offenses/my_offenses/ - Get current user's offenses (employee)
    """
    serializer_class = OffenseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Offense.objects.select_related('employee', 'created_by').filter(is_deleted=False)

        # Only admin can see all offenses
        if user.role == 'admin':
            # Optional filters
            employee_id = self.request.query_params.get('employee_id')
            offense_type = self.request.query_params.get('offense_type')
            severity_level = self.request.query_params.get('severity_level')
            date_from = self.request.query_params.get('date_from')
            date_to = self.request.query_params.get('date_to')

            if employee_id:
                queryset = queryset.filter(employee_id=employee_id)
            if offense_type:
                queryset = queryset.filter(offense_type=offense_type)
            if severity_level:
                queryset = queryset.filter(severity_level=severity_level)
            if date_from:
                queryset = queryset.filter(date__gte=date_from)
            if date_to:
                queryset = queryset.filter(date__lte=date_to)
        else:
            # Employees can only see their own offenses
            queryset = queryset.filter(employee=user)

        return queryset.order_by('-date', '-created_at')

    def create(self, request, *args, **kwargs):
        """Only admin can create offenses."""
        if request.user.role != 'admin':
            return Response(
                {'detail': 'Only admin can create offenses.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Set the created_by field to the current user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Only admin can update offenses."""
        if request.user.role != 'admin':
            return Response(
                {'detail': 'Only admin can update offenses.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Only admin can delete offenses."""
        if request.user.role != 'admin':
            return Response(
                {'detail': 'Only admin can delete offenses.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_offenses(self, request):
        """Get current user's offenses (for employee view)."""
        offenses = self.get_queryset().filter(employee=request.user)
        serializer = self.get_serializer(offenses, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAdminOnly])
    def statistics(self, request):
        """
        Get offense statistics for all employees or specific employee.
        Query params:
        - employee_id: Filter by specific employee
        - at_limit: Filter employees at or above offense limit (default: 3)
        """
        from django.db.models import Count
        from users.models import CustomUser

        # Get filter parameters
        employee_id = request.query_params.get('employee_id')
        at_limit = request.query_params.get('at_limit', 'false').lower() == 'true'
        limit_threshold = int(request.query_params.get('limit_threshold', 3))

        # Build base query - get users with technician or clerk role
        employees = CustomUser.objects.filter(is_deleted=False, role__in=['technician', 'clerk'])
        if employee_id:
            employees = employees.filter(id=employee_id)

        # Build statistics
        statistics = []
        for employee in employees:
            offense_counts = Offense.objects.filter(employee=employee).values('offense_type').annotate(count=Count('id'))
            severity_counts = Offense.objects.filter(employee=employee).values('severity_level').annotate(count=Count('id'))

            # Convert to dictionaries for easy access
            offense_dict = {item['offense_type']: item['count'] for item in offense_counts}
            severity_dict = {item['severity_level']: item['count'] for item in severity_counts}

            total_offenses = Offense.get_offense_count(employee)
            is_at_limit = Offense.is_at_limit(employee, limit_threshold)

            # Get last offense date
            last_offense = Offense.objects.filter(employee=employee).order_by('-date').first()
            last_offense_date = last_offense.date if last_offense else None

            # Filter by limit if requested
            if at_limit and not is_at_limit:
                continue

            statistics.append({
                'employee_id': employee.id,
                'employee_name': employee.get_full_name(),
                'total_offenses': total_offenses,
                'awol_count': offense_dict.get('AWOL', 0),
                'late_count': offense_dict.get('LATE', 0),
                'curfew_count': offense_dict.get('CURFEW', 0),
                'other_count': offense_dict.get('OTHER', 0),
                'warning_count': severity_dict.get('WARNING', 0),
                'suspension_count': severity_dict.get('SUSPENSION', 0),
                'termination_count': severity_dict.get('TERMINATION', 0),
                'is_at_limit': is_at_limit,
                'last_offense_date': last_offense_date,
            })

        serializer = OffenseStatisticsSerializer(statistics, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def offense_history(self, request, pk=None):
        """Get offense history for a specific employee."""
        employee_id = pk
        offenses = Offense.objects.filter(employee_id=employee_id).order_by('-date')
        serializer = self.get_serializer(offenses, many=True)
        return Response(serializer.data)


class OvertimeRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for overtime request management.

    Permissions:
    - Admin/Manager: Can view all, approve/reject requests
    - Employees: Can view and create their own requests
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'approve':
            return OvertimeRequestApproveSerializer
        return OvertimeRequestSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = OvertimeRequest.objects.all().select_related("employee", "approved_by")

        # Filter by employee for non-admin users
        if user.role != 'admin':
            queryset = queryset.filter(employee=user)

        # Filter parameters
        employee_id = self.request.query_params.get('employee')
        approved = self.request.query_params.get('approved')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        if approved is not None:
            queryset = queryset.filter(approved=approved.lower() == 'true')
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        return queryset.order_by('-date', '-created_at')

    def perform_create(self, serializer):
        """Create overtime request for the current user if not specified"""
        user = self.request.user
        # If employee not specified and user is not admin, use current user
        if 'employee' not in serializer.validated_data and user.role != 'admin':
            serializer.save(employee=user)
        else:
            serializer.save()

    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        """Approve or reject an overtime request"""
        overtime_request = self.get_object()

        # Only admin can approve
        if request.user.role != 'admin':
            return Response(
                {"detail": "You don't have permission to approve overtime requests."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(overtime_request, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            serializer.save(approved_by=request.user)
        except ValidationError as e:
            # Catch validation error from signal (non-draft payroll exists)
            return Response(
                {"detail": str(e.message) if hasattr(e, 'message') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Notify employee
        from notifications.models import Notification, NotificationType
        is_approved = serializer.validated_data.get('approved', False)
        if is_approved:
            Notification.objects.create(
                user=overtime_request.employee,
                type=NotificationType.OVERTIME_APPROVED,
                title="Overtime Request Approved",
                message=f"Your overtime request for {overtime_request.date} has been approved.",
                data={"overtime_request_id": overtime_request.id, "date": str(overtime_request.date)},
            )
        else:
            Notification.objects.create(
                user=overtime_request.employee,
                type=NotificationType.OVERTIME_REJECTED,
                title="Overtime Request Rejected",
                message=f"Your overtime request for {overtime_request.date} has been rejected.",
                data={"overtime_request_id": overtime_request.id, "date": str(overtime_request.date)},
            )

        return Response(serializer.data)


class HalfDayScheduleViewSet(SoftDeleteViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing half-day schedules.
    
    Admin can mark specific dates as forced half-days.
    On those dates, all employees' attendance will be capped at 4 paid hours.
    
    Permissions:
    - Admin/Manager: Full access (create, update, delete, view all)
    - Others: Read-only access
    
    Endpoints:
    - GET /api/attendance/half-day-schedules/ - List all half-day schedules
    - POST /api/attendance/half-day-schedules/ - Create (admin/manager only)
    - GET /api/attendance/half-day-schedules/{id}/ - Get detail
    - PUT/PATCH /api/attendance/half-day-schedules/{id}/ - Update (admin/manager only)
    - DELETE /api/attendance/half-day-schedules/{id}/ - Soft delete (admin/manager only)
    """
    allow_hard_delete = True
    serializer_class = HalfDayScheduleSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Get non-deleted half-day schedules."""
        queryset = HalfDaySchedule.objects.filter(is_deleted=False).select_related('created_by')
        
        # Filter by schedule type if provided
        schedule_type = self.request.query_params.get('schedule_type')
        if schedule_type:
            queryset = queryset.filter(schedule_type=schedule_type)
        
        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        date = self.request.query_params.get('date')
        
        if date:
            queryset = queryset.filter(date=date)
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        return queryset
    
    def get_permissions(self):
        """Only admin can create, update, delete."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOnly()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        """Create schedule and auto-mark employees as SHOP_CLOSED if applicable."""
        schedule = serializer.save()

        if schedule.schedule_type == 'shop_closed':
            self._auto_mark_shop_closed(schedule)

    def _auto_mark_shop_closed(self, schedule):
        """Auto-create SHOP_CLOSED attendance for all payroll employees."""
        from decimal import Decimal
        from users.models import CustomUser

        employees = CustomUser.objects.filter(
            is_active=True,
            is_deleted=False,
            include_in_payroll=True,
        ).exclude(role='admin')

        for employee in employees:
            attendance, created = DailyAttendance.objects.get_or_create(
                employee=employee,
                date=schedule.date,
                defaults={'attendance_type': 'PENDING'},
            )
            # Skip if already on leave or already clocked in (emergency service)
            if attendance.attendance_type == 'LEAVE':
                continue
            if attendance.clock_in:
                continue

            attendance.attendance_type = 'SHOP_CLOSED'
            attendance.consecutive_absences = 0
            attendance.is_awol = False
            attendance.clock_in = None
            attendance.clock_out = None
            attendance.total_hours = Decimal('0.00')
            attendance.paid_hours = Decimal('0.00')
            attendance.break_hours = Decimal('0.00')
            attendance.is_late = False
            attendance.late_minutes = 0
            attendance.late_penalty_amount = Decimal('0.00')
            attendance.status = 'APPROVED'
            attendance.notes = f'Shop Closed - {schedule.reason}' if schedule.reason else 'Shop Closed'
            attendance.save()


class WorkRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing work requests on shop-closed days.

    Employees can request to work on shop-closed days.
    Admin can approve/decline requests (single or batch).
    When approved, the SHOP_CLOSED attendance record is deleted so the
    employee can clock in/out normally.
    """
    serializer_class = WorkRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = WorkRequest.objects.select_related(
            'employee', 'reviewed_by',
        )
        user = self.request.user

        # Non-admin users can only see their own requests
        if user.role not in ('admin', 'manager'):
            queryset = queryset.filter(employee=user)

        # Filters
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        date_filter = self.request.query_params.get('date')
        if date_filter:
            queryset = queryset.filter(date=date_filter)

        employee_filter = self.request.query_params.get('employee')
        if employee_filter:
            queryset = queryset.filter(employee_id=employee_filter)

        return queryset

    def perform_create(self, serializer):
        """Employee creates a request for themselves."""
        work_request = serializer.save(employee=self.request.user)

        # Notify admins
        from notifications.models import Notification
        from users.models import CustomUser
        admins = CustomUser.objects.filter(role='admin', is_active=True, is_deleted=False)
        for admin_user in admins:
            Notification.objects.create(
                user=admin_user,
                type="system",
                title="New Work Request",
                message=f"{self.request.user.get_full_name()} has requested to work on {work_request.date}.",
                data={"work_request_id": work_request.id, "date": str(work_request.date)},
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOnly])
    def approve(self, request, pk=None):
        """Approve a work request and delete the SHOP_CLOSED attendance."""
        work_request = self.get_object()
        if work_request.status != 'pending':
            return Response(
                {'detail': f'Cannot approve a request with status \'{work_request.status}\'.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        self._approve_request(work_request, request.user)
        return Response(WorkRequestSerializer(work_request).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOnly])
    def decline(self, request, pk=None):
        """Decline a work request."""
        work_request = self.get_object()
        if work_request.status != 'pending':
            return Response(
                {'detail': f'Cannot decline a request with status \'{work_request.status}\'.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        decline_reason = request.data.get('reason', '')

        work_request.status = 'declined'
        work_request.decline_reason = decline_reason
        work_request.reviewed_by = request.user
        work_request.reviewed_at = timezone.now()
        work_request.save()

        # Notify employee
        from notifications.models import Notification, NotificationType
        Notification.objects.create(
            user=work_request.employee,
            type=NotificationType.WORK_REQUEST_DECLINED,
            title="Work Request Declined",
            message=f"Your request to work on {work_request.date} has been declined."
                    + (f" Reason: {decline_reason}" if decline_reason else ""),
            data={"work_request_id": work_request.id, "date": str(work_request.date)},
        )

        return Response(WorkRequestSerializer(work_request).data)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOnly], url_path='batch-approve')
    def batch_approve(self, request):
        """Approve multiple work requests at once."""
        ids = request.data.get('ids', [])
        if not ids:
            return Response(
                {'detail': 'No request IDs provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pending = WorkRequest.objects.filter(id__in=ids, status='pending').select_related('employee')
        approved_count = 0
        for wr in pending:
            self._approve_request(wr, request.user)
            approved_count += 1

        return Response({'approved_count': approved_count})

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOnly], url_path='batch-decline')
    def batch_decline(self, request):
        """Decline multiple work requests at once."""
        ids = request.data.get('ids', [])
        reason = request.data.get('reason', '')
        if not ids:
            return Response(
                {'detail': 'No request IDs provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from notifications.models import Notification, NotificationType

        pending = WorkRequest.objects.filter(id__in=ids, status='pending').select_related('employee')
        declined_count = 0
        for wr in pending:
            wr.status = 'declined'
            wr.decline_reason = reason
            wr.reviewed_by = request.user
            wr.reviewed_at = timezone.now()
            wr.save()

            Notification.objects.create(
                user=wr.employee,
                type=NotificationType.WORK_REQUEST_DECLINED,
                title="Work Request Declined",
                message=f"Your request to work on {wr.date} has been declined."
                        + (f" Reason: {reason}" if reason else ""),
                data={"work_request_id": wr.id, "date": str(wr.date)},
            )
            declined_count += 1

        return Response({'declined_count': declined_count})

    @action(detail=False, methods=['get'], url_path='my-request')
    def my_request(self, request):
        """Get the current user's work request for a specific date."""
        date_param = request.query_params.get('date')
        if not date_param:
            return Response(
                {'detail': 'Date parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        work_request = WorkRequest.objects.filter(
            employee=request.user,
            date=date_param,
        ).order_by('-created_at').first()

        if not work_request:
            return Response(None, status=status.HTTP_200_OK)

        return Response(WorkRequestSerializer(work_request).data)

    def _approve_request(self, work_request, admin_user):
        """Approve a single work request and clear the SHOP_CLOSED attendance."""
        work_request.status = 'approved'
        work_request.reviewed_by = admin_user
        work_request.reviewed_at = timezone.now()
        work_request.save()

        # Delete the SHOP_CLOSED/ABSENT attendance record so employee can clock in/out
        DailyAttendance.objects.filter(
            employee=work_request.employee,
            date=work_request.date,
            attendance_type__in=['SHOP_CLOSED', 'ABSENT'],
            clock_in__isnull=True,
        ).delete()

        # Notify employee
        from notifications.models import Notification, NotificationType
        if work_request.employee.is_active:
            Notification.objects.create(
                user=work_request.employee,
                type=NotificationType.WORK_REQUEST_APPROVED,
                title="Work Request Approved",
                message=f"Your request to work on {work_request.date} has been approved. You can now clock in/out.",
                data={"work_request_id": work_request.id, "date": str(work_request.date)},
            )
