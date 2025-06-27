from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("authentication.api.urls"), name="auth"),
    path("api/users/", include("users.api.urls"), name="users"),
    path("api/clients/", include("clients.api.urls"), name="clients"),
    path("api/inventory/", include("inventory.api.urls"), name="inventory"),
    path("api/logs/", include("logs.api.urls"), name="logs"),
    path("api/sales/", include("sales.api.urls"), name="sales"),
    path("api/services/", include("services.api.urls"), name="services"),
    path("api/expenses/", include("expenses.api.urls"), name="expenses"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
