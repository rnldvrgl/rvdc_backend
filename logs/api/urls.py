from django.urls import path
from .views import ActivityLogListView

urlpatterns = [
    path("logs/", ActivityLogListView.as_view(), name="activity-log-list"),
]
