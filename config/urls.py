from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("authentication.api.urls"), name="auth"),
    path("api/users/", include("users.api.urls"), name="users"),
    path("api/clients/", include("clients.api.urls")),
    path("api/inventory/", include("inventory.api.urls"), name="inventory"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
