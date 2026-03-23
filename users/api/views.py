from rest_framework import generics, permissions, filters, viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView
from utils.query import filter_by_date_range
from django.utils import timezone
from users.models import CustomUser, SystemSettings, CashAdvanceMovement
from users.api.serializers import EmployeesSerializer, UserSerializer, SystemSettingsSerializer, CashAdvanceMovementSerializer
from django_filters.rest_framework import DjangoFilterBackend


# List all users (admin only)
class UserListView(generics.ListAPIView):
    queryset = CustomUser.all_objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = ["username", "contact_number", "first_name", "last_name", "role"]
    search_fields = ["username", "contact_number", "first_name", "last_name"]
    ordering_fields = "__all__"

    def get_queryset(self):
        return filter_by_date_range(self.request, super().get_queryset())


# Admin: view, update, or soft delete any specific user
class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = CustomUser.all_objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_object(self):
        try:
            user = self.queryset.get(pk=self.kwargs["pk"])
            if user.is_deleted:
                raise NotFound(
                    detail="User not found."
                )  # Prevent accessing soft-deleted users
            return user
        except CustomUser.DoesNotExist:
            raise NotFound(detail="User not found.")

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.is_active = False
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["is_deleted", "is_active", "deleted_at"])

    def get_serializer_context(self):
        return {"request": self.request}


class EmployeesListView(generics.ListCreateAPIView):
    serializer_class = EmployeesSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = CustomUser.objects.exclude(role="admin").filter(is_deleted=False)
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = [
        "username",
        "contact_number",
        "first_name",
        "last_name",
        "email",
        "address",
        "province",
        "city",
        "barangay",
        "role",
    ]
    search_fields = [
        "username",
        "contact_number",
        "first_name",
        "last_name",
        "email",
        "address",
        "province",
        "city",
        "barangay",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        qs = CustomUser.objects.filter(is_deleted=False)
        if self.request.query_params.get("include_admins") != "true":
            qs = qs.exclude(role="admin")
        return filter_by_date_range(self.request, qs)


class UseraDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EmployeesSerializer
    queryset = CustomUser.objects.filter(is_deleted=False)
    permission_classes = [permissions.IsAuthenticated]

    def filter_queryset(self, queryset):
        return queryset

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.is_active = False
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["is_deleted", "is_active", "deleted_at"])

    def get_serializer_context(self):
        return {"request": self.request}


class EmployeeArchivedListView(generics.ListAPIView):
    """List all archived (soft-deleted) employees."""
    serializer_class = EmployeesSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = [
        "username", "contact_number", "first_name", "last_name",
        "email", "address", "province", "city", "barangay",
    ]
    search_fields = [
        "username", "contact_number", "first_name", "last_name",
        "email", "address", "province", "city", "barangay",
    ]
    ordering_fields = "__all__"

    def get_queryset(self):
        return CustomUser.all_objects.exclude(role="admin").filter(is_deleted=True)


class EmployeeRestoreView(APIView):
    """Restore an archived employee."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        from django.shortcuts import get_object_or_404
        instance = get_object_or_404(CustomUser.all_objects.all(), pk=pk)
        if not instance.is_deleted:
            return Response(
                {"detail": "This record is not archived."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.is_deleted = False
        instance.is_active = True
        instance.deleted_at = None
        instance.save(update_fields=["is_deleted", "is_active", "deleted_at"])
        serializer = EmployeesSerializer(instance, context={"request": request})
        return Response(serializer.data)


class MyProfileView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        if self.request.user.is_deleted:
            raise NotFound(detail="User not found.")
        return self.request.user

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()

    def get_serializer_context(self):
        return {"request": self.request}


class SystemSettingsView(generics.RetrieveUpdateAPIView):
    """
    GET: Retrieve system settings (any authenticated user can view)
    PUT/PATCH: Update system settings (admin only)
    """
    serializer_class = SystemSettingsSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        """Always return the singleton settings instance"""
        return SystemSettings.get_settings()
    
    def get_permissions(self):
        """Allow any authenticated user to view, but only admins to update"""
        if self.request.method in ['PUT', 'PATCH']:
            return [permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]


class CashAdvanceMovementViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing cash ban balance movements.
    - List: View all movements (admin/manager) or own movements (employee)
    - Create: Record a new movement — credit (+) or debit (-) (admin/manager only)
    - Retrieve/Delete: Manage specific movement (admin/manager only)
    """
    serializer_class = CashAdvanceMovementSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ['employee', 'date', 'movement_type']
    search_fields = ['employee__first_name', 'employee__last_name', 'description', 'reference']
    ordering_fields = ['date', 'amount', 'created_at']
    ordering = ['-date', '-created_at']

    def get_queryset(self):
        """
        Admin/Manager: See all movements
        Other users: See only their own movements
        """
        queryset = CashAdvanceMovement.objects.filter(is_deleted=False).select_related(
            'employee', 'created_by'
        )

        user = self.request.user
        if user.role in ['admin', 'manager']:
            return filter_by_date_range(self.request, queryset)
        else:
            return queryset.filter(employee=user)

    def get_permissions(self):
        """Only admin/manager can create, update, or delete"""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdminOrManager()]
        return [permissions.IsAuthenticated()]

    def perform_destroy(self, instance):
        """Soft delete and reverse the balance change (only if movement was already applied)"""
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted'])
        # Only reverse the balance change if the movement was already applied (not pending)
        if not instance.is_pending:
            if instance.movement_type == CashAdvanceMovement.MovementType.CREDIT:
                instance.employee.cash_ban_balance -= instance.amount
            else:
                instance.employee.cash_ban_balance += instance.amount
            instance.employee.save(update_fields=['cash_ban_balance'])


class IsAdminOrManager(permissions.BasePermission):
    """Permission class to check if user is admin or manager"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['admin', 'manager']


class ServerMaintenanceView(APIView):
    """
    Admin-only endpoint for server maintenance tasks.
    GET  — Disk, memory, Docker stats, container info, cron jobs, management commands
    POST — Cleanup actions, restart containers, view logs, run management commands
    """
    permission_classes = [permissions.IsAdminUser]

    # Defined cron schedule (runs on host, not in container)
    CRON_JOBS = [
        {"id": "auto_close_attendance", "schedule": "Daily 9:00 PM", "description": "Auto-close open attendance sessions for employees who forgot to clock out", "log_file": "cron-auto-close-attendance.log", "category": "attendance"},
        {"id": "mark_daily_absences", "schedule": "Daily 11:30 PM", "description": "Mark employees absent if no clock-in/out and no approved leave", "log_file": "cron-mark-absences.log", "category": "attendance"},
        {"id": "delete_old_notifications", "schedule": "Daily 2:00 AM", "description": "Delete read notifications older than 7 days", "log_file": "cron-delete-old-notifications.log", "category": "maintenance"},
        {"id": "cleanup_archived_quotations", "schedule": "Daily 3:00 AM", "description": "Delete archived quotations older than 14 days", "log_file": "cron-cleanup-archived-quotations.log", "category": "maintenance"},
        {"id": "truncate_large_logs", "schedule": "Daily 5:00 AM", "description": "Truncate cron log files over 10MB, keep last 500 lines", "log_file": "cron-log-maintenance.log", "category": "maintenance"},
        {"id": "disk_usage_check", "schedule": "Daily 6:00 AM", "description": "Monitor disk usage, auto-cleanup at 90%+ (apt cache, journal, Docker)", "log_file": "cron-disk-usage.log", "category": "maintenance"},
        {"id": "weekly_attendance_payroll_fix", "schedule": "Friday 11:00 PM", "description": "Verify and fix attendance for the past week, then refresh payroll for Saturday payday", "log_file": "cron-weekly-attendance-payroll-fix.log", "category": "payroll"},
        {"id": "docker_system_prune", "schedule": "Sunday 3:00 AM", "description": "Remove unused containers, networks, and dangling images", "log_file": "cron-docker-prune.log", "category": "maintenance"},
        {"id": "cleanup_unused_images", "schedule": "Sunday 3:30 AM", "description": "Delete unused user profile images not linked to any employee", "log_file": "cron-cleanup-images.log", "category": "maintenance"},
        {"id": "update_holiday_years", "schedule": "Jan 1, 2:00 AM", "description": "Shift all holidays to the next calendar year", "log_file": "cron-yearly-update-holidays.log", "category": "payroll"},
        {"id": "replenish_leave_balances", "schedule": "Jan 1, 3:00 AM", "description": "Reset annual leave balances (7 sick, 3 emergency days)", "log_file": "cron-yearly-replenish-leaves.log", "category": "attendance"},
        {"id": "archive_old_payrolls", "schedule": "Jan 2, 2:00 AM", "description": "Export and delete payroll data from the previous year", "log_file": "cron-yearly-archive-payrolls.log", "category": "payroll"},
    ]

    # Management commands safe for manual triggering
    TRIGGERABLE_COMMANDS = [
        {"id": "auto_close_attendance", "label": "Auto-Close Attendance", "description": "Close any open attendance sessions", "app": "attendance", "category": "attendance", "destructive": False},
        {"id": "mark_daily_absences", "label": "Mark Daily Absences", "description": "Mark employees absent for today if no attendance record", "app": "attendance", "category": "attendance", "destructive": False},
        {"id": "fix_attendance_time_entries", "label": "Fix Attendance Entries", "description": "Recalculate paid hours, lateness, and penalties for all attendance records", "app": "attendance", "args": ["--verify-only"], "category": "attendance", "destructive": False},
        {"id": "recalculate_pending_attendance", "label": "Recalculate Attendance", "description": "Recompute attendance metrics for pending records", "app": "attendance", "category": "attendance", "destructive": False},
        {"id": "refresh_payroll_from_attendance", "label": "Refresh Payroll", "description": "Recompute payroll calculations from attendance data", "app": "payroll", "args": ["--force"], "category": "payroll", "destructive": False},
        {"id": "delete_old_notifications", "label": "Delete Old Notifications", "description": "Remove read notifications older than 7 days", "app": "notifications", "args": ["--all", "--days", "7"], "category": "maintenance", "destructive": False},
        {"id": "cleanup_unused_images", "label": "Cleanup Unused Images", "description": "Delete orphaned profile images not linked to any user", "app": "users", "category": "maintenance", "destructive": False},
        {"id": "cleanup_archived_quotations", "label": "Cleanup Archived Quotations", "description": "Delete archived quotations older than 14 days", "app": "quotations", "args": ["--days", "14"], "category": "maintenance", "destructive": False},
        {"id": "recalculate_remittances", "label": "Recalculate Remittances", "description": "Recalculate sales totals on all remittance records", "app": "remittances", "category": "sales", "destructive": False},
        {"id": "recalculate_service_revenue", "label": "Recalculate Service Revenue", "description": "Recalculate revenue figures for all services", "app": "services", "category": "sales", "destructive": False},
        {"id": "find_duplicate_items", "label": "Find Duplicate Items", "description": "Scan inventory for duplicate items by name", "app": "inventory", "category": "inventory", "destructive": False},
        {"id": "remove_duplicate_clients", "label": "Remove Duplicate Clients", "description": "Remove duplicate client records by contact number, keeping the oldest", "app": "clients", "category": "maintenance", "destructive": True},
        {"id": "add_philippine_holidays", "label": "Add PH Holidays", "description": "Add Philippine holidays for the current year (skip existing)", "app": "payroll", "args": ["--skip-existing"], "category": "payroll", "destructive": False},
    ]

    def get(self, request):
        """Return server stats: disk, memory, docker, containers."""
        import shutil
        import subprocess
        import os

        result = {}

        # Disk usage
        total, used, free = shutil.disk_usage("/")
        result["disk"] = {
            "total_gb": round(total / (1024 ** 3), 2),
            "used_gb": round(used / (1024 ** 3), 2),
            "free_gb": round(free / (1024 ** 3), 2),
            "percent_used": round((used / total) * 100, 1),
        }

        # Memory usage
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = {}
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]  # value in kB
                        meminfo[key] = int(val)
                total_mem = meminfo.get("MemTotal", 0)
                available = meminfo.get("MemAvailable", 0)
                used_mem = total_mem - available
                result["memory"] = {
                    "total_gb": round(total_mem / (1024 ** 2), 2),
                    "used_gb": round(used_mem / (1024 ** 2), 2),
                    "available_gb": round(available / (1024 ** 2), 2),
                    "percent_used": round((used_mem / total_mem) * 100, 1) if total_mem else 0,
                }
        except (FileNotFoundError, ValueError, ZeroDivisionError):
            result["memory"] = None

        # Docker disk usage (if socket available)
        try:
            docker_output = subprocess.run(
                ["docker", "system", "df", "--format", "{{.Type}}\t{{.Size}}\t{{.Reclaimable}}"],
                capture_output=True, text=True, timeout=10,
            )
            if docker_output.returncode == 0:
                lines = docker_output.stdout.strip().split("\n")
                result["docker"] = []
                for line in lines:
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        reclaimable = parts[2].strip()
                        # Sanitize negative/malformed reclaimable values
                        if reclaimable.startswith("-") or "e+" in reclaimable or "e-" in reclaimable:
                            reclaimable = "0B (0%)"
                        result["docker"].append({
                            "type": parts[0],
                            "size": parts[1],
                            "reclaimable": reclaimable,
                        })
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result["docker"] = None

        # Docker containers status
        try:
            containers_output = subprocess.run(
                [
                    "docker", "ps", "-a",
                    "--format", "{{.Names}}\t{{.Status}}\t{{.State}}\t{{.Size}}"
                ],
                capture_output=True, text=True, timeout=10,
            )
            if containers_output.returncode == 0 and containers_output.stdout.strip():
                result["containers"] = []
                for line in containers_output.stdout.strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        result["containers"].append({
                            "name": parts[0],
                            "status": parts[1],
                            "state": parts[2],
                            "size": parts[3] if len(parts) > 3 else "",
                        })
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result["containers"] = None

        # Top large files in media directory
        media_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "media")
        try:
            large_files = []
            for dirpath, _, filenames in os.walk(media_root):
                for fname in filenames:
                    fpath = os.path.join(dirpath, fname)
                    try:
                        fsize = os.path.getsize(fpath)
                        if fsize > 1 * 1024 * 1024:  # > 1MB
                            large_files.append({
                                "path": os.path.relpath(fpath, media_root),
                                "size_mb": round(fsize / (1024 * 1024), 2),
                            })
                    except OSError:
                        pass
            large_files.sort(key=lambda x: x["size_mb"], reverse=True)
            result["large_media_files"] = large_files[:20]
            # Total media size
            total_media = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fns in os.walk(media_root) for f in fns
                if os.path.isfile(os.path.join(dp, f))
            )
            result["media_total_mb"] = round(total_media / (1024 * 1024), 2)
        except (FileNotFoundError, OSError):
            result["large_media_files"] = []
            result["media_total_mb"] = 0

        # Cron jobs with log info
        host_logs_dir = "/host-logs"
        cron_jobs = []
        for job in self.CRON_JOBS:
            job_info = {**job}
            log_path = os.path.join(host_logs_dir, job["log_file"])
            if os.path.isfile(log_path):
                try:
                    stat = os.stat(log_path)
                    job_info["log_size_kb"] = round(stat.st_size / 1024, 1)
                    job_info["last_modified"] = timezone.datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.get_current_timezone()
                    ).isoformat()
                    # Read last few lines to detect success/failure
                    with open(log_path, "r", errors="replace") as f:
                        lines = f.readlines()
                        tail = "".join(lines[-5:]) if lines else ""
                        if "✅" in tail or "Success" in tail or "complete" in tail.lower():
                            job_info["last_status"] = "success"
                        elif "❌" in tail or "Failed" in tail or "Error" in tail:
                            job_info["last_status"] = "error"
                        else:
                            job_info["last_status"] = "unknown"
                except OSError:
                    job_info["last_status"] = "no_log"
            else:
                job_info["last_status"] = "no_log"
                job_info["log_size_kb"] = 0
                job_info["last_modified"] = None
            cron_jobs.append(job_info)
        result["cron_jobs"] = cron_jobs

        # Available management commands for manual triggering
        result["management_commands"] = self.TRIGGERABLE_COMMANDS

        return Response(result)

    def post(self, request):
        """Run maintenance actions."""
        import subprocess
        import logging
        import threading

        logger = logging.getLogger(__name__)
        action_type = request.data.get("action", "full_cleanup")

        allowed_actions = [
            "docker_prune", "log_cleanup", "full_cleanup",
            "restart_containers", "container_logs",
            "run_command", "view_cron_log",
        ]
        if action_type not in allowed_actions:
            return Response(
                {"error": f"Invalid action. Allowed: {allowed_actions}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Synchronous actions (fast, return data immediately) ---

        # Container logs
        if action_type == "container_logs":
            container = request.data.get("container", "rvdc_backend-api-1")
            tail_lines = min(int(request.data.get("lines", 100)), 500)
            allowed_containers = ["rvdc_backend-api-1", "rvdc_backend-redis-1", "rvdc_backend-db-1"]
            if container not in allowed_containers:
                return Response(
                    {"error": f"Container not allowed. Allowed: {allowed_containers}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                logs_result = subprocess.run(
                    ["docker", "logs", "--tail", str(tail_lines), container],
                    capture_output=True, text=True, timeout=15,
                )
                log_output = logs_result.stdout or logs_result.stderr or ""
                return Response({
                    "success": True,
                    "action": "container_logs",
                    "container": container,
                    "logs": log_output[-10000:],
                })
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                return Response({
                    "success": False,
                    "action": "container_logs",
                    "error": str(e)[:200],
                })

        # View cron log file
        if action_type == "view_cron_log":
            import os
            log_file = request.data.get("log_file", "")
            # Validate against known cron job log files only
            allowed_log_files = {job["log_file"] for job in self.CRON_JOBS}
            if log_file not in allowed_log_files:
                return Response(
                    {"error": "Log file not allowed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            log_path = os.path.join("/host-logs", log_file)
            try:
                with open(log_path, "r", errors="replace") as f:
                    content = f.read()
                # Return last 15000 chars
                return Response({
                    "success": True,
                    "action": "view_cron_log",
                    "log_file": log_file,
                    "logs": content[-15000:],
                })
            except FileNotFoundError:
                return Response({
                    "success": True,
                    "action": "view_cron_log",
                    "log_file": log_file,
                    "logs": "No log file found. This job may not have run yet.",
                })
            except OSError as e:
                return Response({
                    "success": False,
                    "action": "view_cron_log",
                    "error": str(e)[:200],
                })

        # --- Background actions (threaded, push result via WebSocket) ---
        user_id = request.user.id
        user_name = request.user.get_full_name()
        container_arg = request.data.get("container", "")
        command_id = request.data.get("command", "")

        # Validate run_command before starting thread
        command_config = None
        if action_type == "run_command":
            command_config = next(
                (cmd for cmd in self.TRIGGERABLE_COMMANDS if cmd["id"] == command_id),
                None,
            )
            if not command_config:
                return Response(
                    {"error": f"Unknown or disallowed command: {command_id}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        def _run_maintenance():
            _logger = logging.getLogger(__name__)
            results = []

            # Docker system prune
            if action_type in ("docker_prune", "full_cleanup"):
                try:
                    prune_result = subprocess.run(
                        ["docker", "system", "prune", "-f"],
                        capture_output=True, text=True, timeout=300,
                    )
                    output = prune_result.stdout.strip()[-500:] if prune_result.stdout else ""
                    results.append({
                        "task": "docker_system_prune",
                        "success": prune_result.returncode == 0,
                        "output": output,
                        "error": prune_result.stderr.strip()[-200:] if prune_result.returncode != 0 else "",
                    })
                except FileNotFoundError:
                    results.append({
                        "task": "docker_system_prune",
                        "success": False,
                        "error": "Docker not available in this environment",
                    })
                except subprocess.TimeoutExpired:
                    results.append({
                        "task": "docker_system_prune",
                        "success": False,
                        "error": "Timed out after 300s",
                    })

                # Image prune (unused images older than 7 days)
                try:
                    img_result = subprocess.run(
                        ["docker", "image", "prune", "-a", "--filter", "until=168h", "-f"],
                        capture_output=True, text=True, timeout=300,
                    )
                    output = img_result.stdout.strip()[-500:] if img_result.stdout else ""
                    results.append({
                        "task": "docker_image_prune",
                        "success": img_result.returncode == 0,
                        "output": output,
                        "error": img_result.stderr.strip()[-200:] if img_result.returncode != 0 else "",
                    })
                except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                    results.append({
                        "task": "docker_image_prune",
                        "success": False,
                        "error": str(e)[:200],
                    })

            # Log cleanup
            if action_type in ("log_cleanup", "full_cleanup"):
                log_files_truncated = 0
                try:
                    import glob
                    import os
                    for log_path in glob.glob("/host-logs/cron-*.log"):
                        try:
                            size = os.path.getsize(log_path)
                            if size > 5 * 1024 * 1024:
                                with open(log_path, "w") as f:
                                    f.write(f"--- Log truncated by admin on {timezone.now().isoformat()} ---\n")
                                log_files_truncated += 1
                        except OSError:
                            pass
                    results.append({
                        "task": "log_cleanup",
                        "success": True,
                        "output": f"Truncated {log_files_truncated} log files over 5MB",
                    })
                except Exception as e:
                    results.append({
                        "task": "log_cleanup",
                        "success": False,
                        "error": str(e)[:200],
                    })

            # Restart containers
            if action_type == "restart_containers":
                allowed_containers = ["rvdc_backend-api-1", "rvdc_backend-redis-1", "rvdc_backend-db-1"]
                targets = [container_arg] if container_arg and container_arg in allowed_containers else (
                    allowed_containers if not container_arg else []
                )
                if not targets and container_arg:
                    results.append({
                        "task": "restart",
                        "success": False,
                        "error": f"Container not allowed. Allowed: {allowed_containers}",
                    })
                for c_name in targets:
                    try:
                        restart_result = subprocess.run(
                            ["docker", "restart", c_name],
                            capture_output=True, text=True, timeout=60,
                        )
                        results.append({
                            "task": f"restart_{c_name}",
                            "success": restart_result.returncode == 0,
                            "output": f"{c_name} restarted" if restart_result.returncode == 0 else "",
                            "error": restart_result.stderr.strip()[:200] if restart_result.returncode != 0 else "",
                        })
                    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                        results.append({
                            "task": f"restart_{c_name}",
                            "success": False,
                            "error": str(e)[:200],
                        })

            # Run management command
            if action_type == "run_command" and command_config:
                from io import StringIO
                from django.core.management import call_command

                cmd_name = command_config["id"]
                cmd_args = command_config.get("args", [])
                try:
                    out = StringIO()
                    err = StringIO()
                    call_command(cmd_name, *cmd_args, stdout=out, stderr=err)
                    output = out.getvalue().strip()
                    error_output = err.getvalue().strip()
                    results.append({
                        "task": cmd_name,
                        "success": True,
                        "output": (output or "Command completed successfully.")[-1000:],
                    })
                    if error_output:
                        results[-1]["output"] += f"\n{error_output[-500:]}"
                except Exception as e:
                    results.append({
                        "task": cmd_name,
                        "success": False,
                        "error": str(e)[:500],
                    })

            all_success = all(r.get("success") for r in results)
            _logger.info(
                "Server maintenance by %s: action=%s results=%s",
                user_name, action_type, results,
            )

            # Push result to admin via WebSocket notification channel
            try:
                from asgiref.sync import async_to_sync
                from channels.layers import get_channel_layer

                channel_layer = get_channel_layer()
                if channel_layer:
                    action_labels = {
                        "docker_prune": "Docker Cleanup",
                        "log_cleanup": "Log Cleanup",
                        "full_cleanup": "Full System Cleanup",
                        "restart_containers": "Container Restart",
                        "run_command": command_config["label"] if command_config else "Command",
                    }
                    label = action_labels.get(action_type, action_type)
                    failed = [r for r in results if not r.get("success")]
                    if all_success:
                        title = f"{label} completed"
                        message = "; ".join(r.get("output", r["task"]) for r in results if r.get("output"))
                        if not message:
                            message = "All tasks completed successfully."
                    else:
                        title = f"{label} finished with issues"
                        message = "; ".join(r.get("error", r["task"]) for r in failed)

                    async_to_sync(channel_layer.group_send)(
                        f"notifications_{user_id}",
                        {
                            "type": "send_notification",
                            "data": {
                                "event": "maintenance_result",
                                "success": all_success,
                                "action": action_type,
                                "title": title,
                                "message": message,
                                "results": results,
                            },
                        },
                    )
            except Exception:
                _logger.exception("Failed to send maintenance result via WebSocket")

        thread = threading.Thread(target=_run_maintenance, daemon=True)
        thread.start()

        action_labels = {
            "docker_prune": "Docker Cleanup",
            "log_cleanup": "Log Cleanup",
            "full_cleanup": "Full System Cleanup",
            "restart_containers": "Container Restart",
            "run_command": command_config["label"] if command_config else "Command",
        }
        return Response({
            "accepted": True,
            "action": action_type,
            "message": f"{action_labels.get(action_type, action_type)} started. You'll be notified when it completes.",
        }, status=status.HTTP_202_ACCEPTED)
