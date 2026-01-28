from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from datetime import date
from django.utils import timezone

from attendance.models import DailyAttendance, LeaveBalance, LeaveRequest
from attendance.api.serializers import (
    DailyAttendanceSerializer,
    ClockInSerializer,
    ClockOutSerializer,
    ApproveAttendanceSerializer,
    RejectAttendanceSerializer,
    LeaveBalanceSerializer,
    LeaveRequestSerializer,
    ApproveLeaveSerializer,
    RejectLeaveSerializer,
)


class IsAdminOrManager(IsAuthenticated):
    """Permission class for admin and manager roles only."""
    
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.role in ['admin', 'manager']


class DailyAttendanceViewSet(viewsets.ModelViewSet):
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
        
        # Admins and managers can see all attendance
        if user.role in ['admin', 'manager']:
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
            # Employees can only see their own attendance
            queryset = queryset.filter(employee=user)
        
        return queryset.select_related('employee', 'approved_by').order_by('-date')

    def create(self, request, *args, **kwargs):
        """Only admin/manager can create attendance records."""
        if request.user.role not in ['admin', 'manager']:
            return Response(
                {'detail': 'Only admin and manager can create attendance records.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().create(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        """Only admin/manager can update attendance records."""
        if request.user.role not in ['admin', 'manager']:
            return Response(
                {'detail': 'Only admin and manager can update attendance records.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete: Only admin/manager can delete."""
        if request.user.role not in ['admin', 'manager']:
            return Response(
                {'detail': 'Only admin and manager can delete attendance records.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        instance = self.get_object()
        instance.is_deleted = True
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=False, methods=["get"])
    def current_status(self, request):
        attendance = (
            DailyAttendance.objects
            .filter(
                employee=request.user,
                date=timezone.localdate(),
                is_deleted=False
            )
            .first()
        )

        if attendance is None:
            return Response(None, status=status.HTTP_200_OK)

        serializer = self.get_serializer(attendance)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
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
        
        # Check if attendance already exists for this employee on this date
        existing = DailyAttendance.objects.filter(
            employee_id=employee_id,
            date=attendance_date,
            is_deleted=False
        ).first()
        
        if existing:
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
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrManager])
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
        for attendance in attendances:
            attendance.approve(request.user)
            approved_count += 1
        
        return Response(
            {
                'detail': f'{approved_count} attendance record(s) approved.',
                'approved_count': approved_count,
            },
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrManager])
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
        for attendance in attendances:
            attendance.reject(request.user, reason=reason)
            rejected_count += 1
        
        return Response(
            {
                'detail': f'{rejected_count} attendance record(s) rejected.',
                'rejected_count': rejected_count,
            },
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['patch'], permission_classes=[IsAdminOrManager])
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
    
    @action(detail=False, methods=["get"])
    def pending_approvals(self, request):
        """Get all pending attendance records (admin/manager only)."""
        if request.user.role not in ["admin", "manager"]:
            return Response(
                {"detail": "Only admin and manager can view pending approvals."},
                status=status.HTTP_403_FORBIDDEN,
            )

        employee_id = request.query_params.get("employee_id")

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
        
        # Admins and managers can see all balances
        if user.role in ['admin', 'manager']:
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
        balance, created = LeaveBalance.objects.get_or_create(
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
        queryset = LeaveRequest.objects.all()
        
        # Admins and managers can see all requests
        if user.role in ['admin', 'manager']:
            employee_id = self.request.query_params.get('employee_id')
            status_filter = self.request.query_params.get('status')
            leave_type = self.request.query_params.get('leave_type')
            
            if employee_id:
                queryset = queryset.filter(employee_id=employee_id)
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            if leave_type:
                queryset = queryset.filter(leave_type=leave_type)
        else:
            # Employees can only see their own requests
            queryset = queryset.filter(employee=user)
        
        return queryset.select_related('employee', 'approved_by').order_by('-date')
    
    def perform_create(self, serializer):
        """Set the employee to the current user if not specified."""
        if self.request.user.role in ['admin', 'manager']:
            # Admin/manager can create for any employee
            serializer.save()
        else:
            # Regular employees can only create for themselves
            serializer.save(employee=self.request.user)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrManager])
    def approve(self, request):
        """
        Approve one or more leave requests.
        
        Required fields:
        - leave_request_ids: List of leave request IDs to approve
        """
        serializer = ApproveLeaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        leave_request_ids = serializer.validated_data['leave_request_ids']
        leave_requests = LeaveRequest.objects.filter(
            id__in=leave_request_ids,
            status='PENDING'
        )
        
        approved_count = 0
        errors = []
        
        for leave_request in leave_requests:
            try:
                leave_request.approve(request.user)
                approved_count += 1
            except Exception as e:
                errors.append({
                    'leave_request_id': leave_request.id,
                    'error': str(e)
                })
        
        response_data = {
            'detail': f'{approved_count} leave request(s) approved.',
            'approved_count': approved_count,
        }
        
        if errors:
            response_data['errors'] = errors
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrManager])
    def reject(self, request):
        """
        Reject one or more leave requests.
        
        Required fields:
        - leave_request_ids: List of leave request IDs to reject
        - reason: Optional rejection reason
        """
        serializer = RejectLeaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        leave_request_ids = serializer.validated_data['leave_request_ids']
        reason = serializer.validated_data.get('reason', '')
        
        leave_requests = LeaveRequest.objects.filter(
            id__in=leave_request_ids,
            status='PENDING'
        )
        
        rejected_count = 0
        for leave_request in leave_requests:
            try:
                leave_request.reject(request.user, reason=reason)
                rejected_count += 1
            except Exception:
                pass
        
        return Response(
            {
                'detail': f'{rejected_count} leave request(s) rejected.',
                'rejected_count': rejected_count,
            },
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=["get"])
    def pending_approvals(self, request):
        """Get all pending attendance records (admin/manager only)."""
        if request.user.role not in ["admin", "manager"]:
            return Response(
                {"detail": "Only admin and manager can view pending approvals."},
                status=status.HTTP_403_FORBIDDEN,
            )

        employee_id = request.query_params.get("employee_id")

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

        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an approved leave request (restore balance)."""
        leave_request = self.get_object()
        
        # Only the employee or admin/manager can cancel
        if leave_request.employee != request.user and request.user.role not in ['admin', 'manager']:
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
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
