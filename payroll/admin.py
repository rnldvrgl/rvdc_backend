from decimal import Decimal

from django.contrib import admin
from django.utils import timezone

from payroll.models import (
    AdditionalEarning,
    DeductionRate,
    Holiday,
    ManualDeduction,
    PayrollSettings,
    WeeklyPayroll,
)


@admin.register(PayrollSettings)
class PayrollSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "shift_start",
        "shift_end",
        "grace_minutes",
        "auto_close_enabled",
        "holiday_day_hours",
        "holiday_regular_pct",
        "holiday_special_pct",
        "regular_holiday_no_work_pays",
        "special_holiday_no_work_pays",
        "overtime_multiplier",
        "night_diff_multiplier",
        "cash_ban_enabled",
        "cash_ban_contribution_amount",
        "updated_at",
    )
    readonly_fields = ("updated_at",)
    fieldsets = (
        ("Shift Settings", {
            "fields": ("shift_start", "shift_end", "grace_minutes", "clock_out_tolerance_minutes", "auto_close_enabled")
        }),
        ("Holiday Settings", {
            "fields": (
                "holiday_day_hours",
                "holiday_regular_pct",
                "holiday_special_pct",
                "regular_holiday_no_work_pays",
                "special_holiday_no_work_pays",
            )
        }),
        ("Overtime & Night Differential", {
            "fields": ("overtime_multiplier", "night_diff_multiplier")
        }),
        ("Cash Ban Contribution", {
            "fields": ("cash_ban_enabled", "cash_ban_contribution_amount"),
            "description": "Automatic contribution to employee cash ban fund when payroll is approved"
        }),
        ("Metadata", {
            "fields": ("updated_at",)
        }),
    )


@admin.register(WeeklyPayroll)
class WeeklyPayrollAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "employee",
        "week_start",
        "regular_hours",
        "approved_ot_hours",
        "total_hours_display",
        "hourly_rate",
        "holiday_pay_total",
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

        "night_diff_hours",
        "approved_ot_hours",
        "gross_pay",

        "night_diff_pay",
        "approved_ot_pay",
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

                                    "night_diff_hours",
                                    "approved_ot_hours",
                                    "total_hours_readonly",

                                ),

            },
        ),
        (
            "Pay Components",
            {

                                "fields": (

                                    "allowances",

                                    "night_diff_pay",
                                    "approved_ot_pay",
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
                obj.approved_ot_hours or Decimal("0")
            )
            return f"{Decimal(total).quantize(Decimal('0.01'))}"
        except Exception:
            return "0.00"

    @admin.display(description="Total hours (readonly)")
    def total_hours_readonly(self, obj: WeeklyPayroll) -> str:
        try:
            total = (obj.regular_hours or Decimal("0")) + (
                obj.approved_ot_hours or Decimal("0")
            )
            return f"{Decimal(total).quantize(Decimal('0.0001'))}"
        except Exception:
            return "0.0000"



    @admin.action(description="Recompute from daily attendance")
    def recompute_from_time_entries(self, request, queryset):
        updated = 0
        for payroll in queryset:

            payroll.compute_from_daily_attendance()

            payroll.save(

                update_fields=[

                    "regular_hours",

                    "night_diff_hours",
                    "approved_ot_hours",
                    "allowances",
                    "gross_pay",

                    "night_diff_pay",
                    "approved_ot_pay",
                    "deductions",
                    "deduction_metadata",
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




@admin.register(Holiday)

class HolidayAdmin(admin.ModelAdmin):

    list_display = ("date", "name", "kind", "is_deleted")

    list_filter = ("kind", "is_deleted", "date")

    search_fields = ("name",)

    date_hierarchy = "date"

    ordering = ("-date",)

    @admin.action(description="Soft delete selected holidays")
    def soft_delete(self, request, queryset):
        queryset.update(is_deleted=True)

    @admin.action(description="Restore selected holidays")
    def restore(self, request, queryset):
        queryset.update(is_deleted=False)

    actions = ("soft_delete", "restore",)


@admin.register(ManualDeduction)
class ManualDeductionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "deduction_type",
        "employee",
        "amount",
        "effective_date",
        "end_date",
        "is_active",
        "applied_date",
        "is_deleted",
    )

    list_filter = ("deduction_type", "is_active", "is_deleted", "effective_date")

    search_fields = ("name", "description", "employee__first_name", "employee__last_name")

    date_hierarchy = "effective_date"

    ordering = ("-created_at",)

    raw_id_fields = ("employee", "created_by")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "description",
                    "deduction_type",
                    "employee",
                    "amount",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "effective_date",
                    "end_date",
                    "applied_date",
                    "is_active",
                )
            },
        ),
        (
            "Meta",
            {
                "classes": ("collapse",),
                "fields": (
                    "created_by",
                    "is_deleted",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at")

    @admin.action(description="Mark as active")
    def mark_active(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Mark as inactive")
    def mark_inactive(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Soft delete selected deductions")
    def soft_delete(self, request, queryset):
        queryset.update(is_deleted=True)

    @admin.action(description="Restore selected deductions")
    def restore(self, request, queryset):
        queryset.update(is_deleted=False)

    actions = ("mark_active", "mark_inactive", "soft_delete", "restore")


@admin.register(DeductionRate)

class DeductionRateAdmin(admin.ModelAdmin):

    list_display = (

        "name",

        "amount",

        "effective_start",

        "effective_end",

        "is_active",

        "created_by",

        "created_at",

    )

    list_filter = ("name", "is_active", "effective_start", "effective_end")

    search_fields = ("name",)

    date_hierarchy = "effective_start"

    ordering = ("name", "-effective_start")

    readonly_fields = ("created_at",)

    @admin.action(description="Activate selected rates")
    def activate_rates(self, request, queryset):
        queryset.update(is_active=True, effective_end=None)

    @admin.action(description="Deactivate selected rates")
    def deactivate_rates(self, request, queryset):
        queryset.update(is_active=False)

    actions = ("activate_rates", "deactivate_rates",)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


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


    @admin.action(description="Approve selected earnings")
    def approve_earnings(self, request, queryset):
        queryset.update(approved=True)

    @admin.action(description="Unapprove selected earnings")
    def unapprove_earnings(self, request, queryset):
        queryset.update(approved=False)

    @admin.action(description="Soft delete selected earnings")
    def soft_delete(self, request, queryset):
        queryset.update(is_deleted=True)

    @admin.action(description="Restore selected earnings")
    def restore(self, request, queryset):
        queryset.update(is_deleted=False)

    actions = ("approve_earnings", "unapprove_earnings", "soft_delete", "restore")
