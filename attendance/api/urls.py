from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DailyAttendanceViewSet, LeaveBalanceViewSet, LeaveRequestViewSet, OffenseViewSet, OvertimeRequestViewSet

router = DefaultRouter()
router.register(r'daily-attendance', DailyAttendanceViewSet, basename='daily-attendance')
router.register(r'leave-balance', LeaveBalanceViewSet, basename='leave-balance')
router.register(r'leave-request', LeaveRequestViewSet, basename='leave-request')
router.register(r'offenses', OffenseViewSet, basename='offense')
router.register(r'overtime-requests', OvertimeRequestViewSet, basename='overtime-request')

urlpatterns = [
    path('', include(router.urls)),
]
