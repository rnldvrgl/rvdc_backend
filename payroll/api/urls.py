from django.urls import include, path
from payroll.api import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r"holidays", views.HolidayViewSet, basename="holiday")
router.register(r"manual-deductions", views.ManualDeductionViewSet, basename="manual-deduction")
router.register(r"tax-brackets", views.TaxBracketViewSet, basename="tax-bracket")
router.register(r"percentage-deductions", views.PercentageDeductionViewSet, basename="percentage-deduction")
router.register(r"government-benefits", views.GovernmentBenefitViewSet, basename="government-benefit")
router.register(r"employee-benefit-overrides", views.EmployeeBenefitOverrideViewSet, basename="employee-benefit-override")

name = "payroll"
urlpatterns = [
    # Weekly payroll generation and preview
    path(
        "weekly-payrolls/generate/",
        views.WeeklyPayrollGenerateView.as_view(),
        name="weeklypayroll-generate",
    ),
    path(
        "weekly-payrolls/bulk-generate/",
        views.WeeklyPayrollBulkGenerateView.as_view(),
        name="weeklypayroll-bulk-generate",
    ),
    path(
        "weekly-payrolls/preview/",
        views.WeeklyPayrollPreviewView.as_view(),
        name="weeklypayroll-preview",
    ),
    # Weekly payroll archive / restore / hard-delete
    path(
        "weekly-payrolls/archived/",
        views.WeeklyPayrollArchivedView.as_view(),
        name="weeklypayroll-archived",
    ),
    path(
        "weekly-payrolls/<int:pk>/restore/",
        views.WeeklyPayrollRestoreView.as_view(),
        name="weeklypayroll-restore",
    ),
    path(
        "weekly-payrolls/<int:pk>/hard-delete/",
        views.WeeklyPayrollHardDeleteView.as_view(),
        name="weeklypayroll-hard-delete",
    ),
    # Weekly payroll summaries
    path(
        "weekly-payrolls/",
        views.WeeklyPayrollListCreateView.as_view(),
        name="weeklypayroll-list",
    ),
    path(
        "weekly-payrolls/<int:pk>/",
        views.WeeklyPayrollDetailView.as_view(),
        name="weeklypayroll-detail",
    ),
    # Download payroll as PDF
    path(
        "weekly-payrolls/<int:pk>/download-pdf/",
        views.WeeklyPayrollDownloadPDFView.as_view(),
        name="weeklypayroll-download-pdf",
    ),
    # Update payroll status
    path(
        "weekly-payrolls/<int:pk>/status/",
        views.WeeklyPayrollUpdateStatusView.as_view(),
        name="weeklypayroll-update-status",
    ),
    # Bulk update status
    path(
        "weekly-payrolls/bulk-update-status/",
        views.WeeklyPayrollBulkUpdateStatusView.as_view(),
        name="weeklypayroll-bulk-update-status",
    ),
    # Weekly payroll filters
    path(
        "weekly-payrolls/filters/",
        views.WeeklyPayrollFiltersView.as_view(),
        name="weeklypayroll-filters",
    ),
    # Recompute a weekly payroll from its time entries
    path(
        "weekly-payrolls/<int:pk>/recompute/",
        views.WeeklyPayrollRecomputeView.as_view(),
        name="weeklypayroll-recompute",
    ),
    # Additional earnings
    path(
        "additional-earnings/",
        views.AdditionalEarningListCreateView.as_view(),
        name="additionalearning-list",
    ),
    path(
        "additional-earnings/<int:pk>/",
        views.AdditionalEarningDetailView.as_view(),
        name="additionalearning-detail",
    ),
    # Payroll Settings (Admin only)
    path(
        "settings/",
        views.PayrollSettingsAdminView.as_view(),
        name="payroll-settings",
    ),
    # Include router URLs (handles holidays CRUD + filters)
    path("", include(router.urls)),
]
