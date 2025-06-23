from django.urls import path
from authentication.api.views import LoginView


app_name = "auth"


urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
]
