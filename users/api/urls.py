from django.urls import path, include
from rest_framework.routers import DefaultRouter
from users.api import views

name = "users"

router = DefaultRouter()
router.register(r'cash-advance-movements', views.CashAdvanceMovementViewSet, basename='cash-advance-movement')

urlpatterns = [
    path("", views.UserListView.as_view(), name="user-list"),
    path("<int:pk>/", views.AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("profile/", views.MyProfileView.as_view(), name="my-profile"),
    path("employees/", views.EmployeesListView.as_view(), name="employee-list"),
    path("employees/archived/", views.EmployeeArchivedListView.as_view(), name="employee-archived"),
    path(
        "employees/<int:pk>/",
        views.UseraDetailView.as_view(),
        name="employee-detail",
    ),
    path(
        "employees/<int:pk>/restore/",
        views.EmployeeRestoreView.as_view(),
        name="employee-restore",
    ),
    path("settings/", views.SystemSettingsView.as_view(), name="system-settings"),
    path("maintenance/", views.ServerMaintenanceView.as_view(), name="server-maintenance"),
    path("maintenance/backups/<str:filename>/", views.BackupDownloadView.as_view(), name="backup-download"),
    path("employees/bulk-template/", views.EmployeeBulkTemplateView.as_view(), name="employee-bulk-template"),
    path("employees/bulk-preview/", views.EmployeeBulkPreviewView.as_view(), name="employee-bulk-preview"),
    path("employees/bulk-update/", views.EmployeeBulkUpdateView.as_view(), name="employee-bulk-update"),
    path("", include(router.urls)),
]
