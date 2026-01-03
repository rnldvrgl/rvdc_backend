
from django.urls import path
from payroll.api import views

name = "payroll"



urlpatterns = [

    # Time entries (clock in/out records)

    path(

        "time-entries/",

        views.TimeEntryListCreateView.as_view(),

        name="timeentry-list",

    ),

    path(

        "time-entries/<int:pk>/",

        views.TimeEntryDetailView.as_view(),

        name="timeentry-detail",

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

    # Recompute a weekly payroll from its time entries

    path(

        "weekly-payrolls/<int:pk>/recompute/",

        views.WeeklyPayrollRecomputeView.as_view(),

        name="weeklypayroll-recompute",

    ),

    # Bulk time entries

    path(

        "time-entries/bulk/",

        views.TimeEntryBulkCreateView.as_view(),

        name="timeentry-bulk-create",

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

    # Sessions Review (auto-closed entries)

    path(

        "sessions/review/",

        views.SessionsReviewListView.as_view(),

        name="sessions-review-list",

    ),

    path(

        "sessions/review/<int:pk>/",

        views.SessionReviewDetailPatchView.as_view(),

        name="session-review-detail",

    ),


    # Overtime Requests
    path(
        "overtime-requests/",
        views.OvertimeRequestListCreateView.as_view(),
        name="overtimerequest-list",
    ),
    path(
        "overtime-requests/<int:pk>/",
        views.OvertimeRequestDetailView.as_view(),
        name="overtimerequest-detail",
    ),
    path(
        "overtime-requests/<int:pk>/approve/",
        views.OvertimeRequestApproveView.as_view(),
        name="overtimerequest-approve",
    ),
]
