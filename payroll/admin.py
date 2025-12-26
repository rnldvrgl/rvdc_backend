from decimal import Decimal

from django.contrib import admin

from payroll.models import AdditionalEarning, PayrollSettings, TimeEntry, WeeklyPayroll


@admin.register(PayrollSettings)
class PayrollSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "shift_start",
        "shift_end",
        "grace_minutes",
        "auto_close_enabled",
        "holiday_special_pct",
        "holiday_regular_pct",
        "updated_at",
    )
    readonly_fields = ("updated_at",)


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "employee",
        "work_date",
        "clock_in",
        "clock_out",
        "unpaid_break_minutes",
        "effective_hours_display",
        "source",
        "approved",
        "is_deleted",
    )
    list_filter = ("approved", "source", "is_deleted", "clock_in")
    search_fields = (
        "employee__username",
        "employee__first_name",
        "employee__last_name",
        "notes",
    )
    date_hierarchy = "clock_in"
    ordering = ("-clock_in",)
    list_select_related = ("employee",)
    list_per_page = 25

    readonly_fields = (
        "work_date",
        "effective_hours_readonly",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Entry",
            {
                "fields": (
                    "employee",
                    "clock_in",
                    "clock_out",
                    "unpaid_break_minutes",
                    "source",
                    "approved",
                    "notes",
                )
            },
        ),
        (
            "Computed",
            {
                "classes": ("collapse",),
                "fields": (
                    "work_date",
                    "effective_hours_readonly",
                ),
            },
        ),
        (
            "Meta",
            {
                "classes": ("collapse",),
                "fields": (
                    "is_deleted",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    @admin.display(description="Eff. Hours")
    def effective_hours_display(self, obj: TimeEntry) -> str:
        try:
            return f"{(obj.effective_hours or Decimal('0')).quantize(Decimal('0.01'))}"
        except Exception:
            return "0.00"

    @admin.display(description="Effective hours (readonly)")
    def effective_hours_readonly(self, obj: TimeEntry) -> str:
        try:
            return (
                f"{(obj.effective_hours or Decimal('0')).quantize(Decimal('0.0001'))}"
            )
        except Exception:
            return "0.0000"


@admin.register(WeeklyPayroll)
class WeeklyPayrollAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "employee",
        "week_start",
        "regular_hours",
        "overtime_hours",
        "total_hours_display",
        "hourly_rate",
        "gross_pay",
        "total_deductions",
        "net_pay",
        "status",
        "is_deleted",
    )
    list_filter = ("status", "is_deleted", "week_start")
    search_fields = (
        "employee__username",
        "employee__first_name",
        "employee__last_name",
        "notes",
    )
    date_hierarchy = "week_start"
    ordering = ("-week_start", "employee_id")
    list_select_related = ("employee",)
    list_per_page = 25

    readonly_fields = (
        "regular_hours",
        "overtime_hours",
        "gross_pay",
        "total_deductions",
        "net_pay",
        "created_at",
        "updated_at",
        "total_hours_readonly",
    )

    fieldsets = (
        (
            "Employee & Period",
            {
                "fields": (
                    "employee",
                    "week_start",
                    "status",
                )
            },
        ),
        (
            "Rates & Thresholds",
            {
                "fields": (
                    "hourly_rate",
                    "overtime_threshold",
                    "overtime_multiplier",
                )
            },
        ),
        (
            "Computed Hours",
            {
                "classes": ("collapse",),
                "fields": (
                    "regular_hours",
                    "overtime_hours",
                    "total_hours_readonly",
                ),
            },
        ),
        (
            "Pay Components",
            {
                "fields": (
                    "allowances",
                    "gross_pay",
                )
            },
        ),
        (
            "Deductions",
            {
                "fields": (
                    "deductions",
                    "total_deductions",
                )
            },
        ),
        (
            "Final",
            {
                "fields": (
                    "net_pay",
                    "notes",
                )
            },
        ),
        (
            "Meta",
            {
                "classes": ("collapse",),
                "fields": (
                    "is_deleted",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    @admin.display(description="Total hours")
    def total_hours_display(self, obj: WeeklyPayroll) -> str:
        try:
            total = (obj.regular_hours or Decimal("0")) + (
                obj.overtime_hours or Decimal("0")
            )
            return f"{Decimal(total).quantize(Decimal('0.01'))}"
        except Exception:
            return "0.00"

    @admin.display(description="Total hours (readonly)")
    def total_hours_readonly(self, obj: WeeklyPayroll) -> str:
        try:
            total = (obj.regular_hours or Decimal("0")) + (
                obj.overtime_hours or Decimal("0")
            )
            return f"{Decimal(total).quantize(Decimal('0.0001'))}"
        except Exception:
            return "0.0000"

    @admin.action(description="Recompute from time entries")
    def recompute_from_time_entries(self, request, queryset):
        updated = 0
        for payroll in queryset:
            payroll.compute_from_time_entries()
            payroll.save(
                update_fields=[
                    "regular_hours",
                    "overtime_hours",
                    "allowances",
                    "gross_pay",
                    "deductions",
                    "total_deductions",
                    "net_pay",
                    "updated_at",
                ]
            )
            updated += 1
        self.message_user(request, f"Recomputed {updated} payroll record(s).")

    @admin.action(description="Mark selected payrolls as Approved")
    def mark_as_approved(self, request, queryset):
        queryset.update(status="approved")

    @admin.action(description="Mark selected payrolls as Paid")
    def mark_as_paid(self, request, queryset):
        queryset.update(status="paid")

    @admin.action(description="Soft delete selected payrolls")
    def soft_delete(self, request, queryset):
        queryset.update(is_deleted=True)

    @admin.action(description="Restore (clear soft delete) for selected payrolls")
    def restore(self, request, queryset):
        queryset.update(is_deleted=False)

    actions = (
        "recompute_from_time_entries",
        "mark_as_approved",
        "mark_as_paid",
        "soft_delete",
        "restore",
    )


@admin.register(AdditionalEarning)
class AdditionalEarningAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "employee",
        "earning_date",
        "category",
        "amount",
        "approved",
        "reference",
        "is_deleted",
    )
    list_filter = ("category", "approved", "is_deleted", "earning_date")
    search_fields = (
        "employee__username",
        "employee__first_name",
        "employee__last_name",
        "description",
        "reference",
    )
    date_hierarchy = "earning_date"
    ordering = ("-earning_date", "employee_id")
    list_select_related = ("employee",)
    list_per_page = 25

    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Earning",
            {
                "fields": (
                    "employee",
                    "earning_date",
                    "category",
                    "amount",
                    "reference",
                    "description",
                    "approved",
                )
            },
        ),
        (
            "Meta",
            {
                "classes": ("collapse",),
                "fields": (
                    "is_deleted",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )
