from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DailyAttendanceViewSet, LeaveBalanceViewSet, LeaveRequestViewSet

router = DefaultRouter()
router.register(r'daily-attendance', DailyAttendanceViewSet, basename='daily-attendance')
router.register(r'leave-balance', LeaveBalanceViewSet, basename='leave-balance')
router.register(r'leave-request', LeaveRequestViewSet, basename='leave-request')

urlpatterns = [
    path('', include(router.urls)),
]
