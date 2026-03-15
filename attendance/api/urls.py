from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DailyAttendanceViewSet, HalfDayScheduleViewSet, LeaveBalanceViewSet, LeaveRequestViewSet, OffenseViewSet, OvertimeRequestViewSet, WorkRequestViewSet

router = DefaultRouter()
router.register(r'daily-attendance', DailyAttendanceViewSet, basename='daily-attendance')
router.register(r'leave-balance', LeaveBalanceViewSet, basename='leave-balance')
router.register(r'leave-request', LeaveRequestViewSet, basename='leave-request')
router.register(r'offenses', OffenseViewSet, basename='offense')
router.register(r'overtime-requests', OvertimeRequestViewSet, basename='overtime-request')
router.register(r'half-day-schedules', HalfDayScheduleViewSet, basename='half-day-schedule')
router.register(r'work-requests', WorkRequestViewSet, basename='work-request')

urlpatterns = [
    path('', include(router.urls)),
]
