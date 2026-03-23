from django.urls import path
from rest_framework.routers import DefaultRouter
from receivables.api.views import ChequeCollectionViewSet
from analytics.api.export_views import ChequeExportView

router = DefaultRouter()
router.register(r"cheques", ChequeCollectionViewSet, basename="cheque")

urlpatterns = [
    path("export-report/", ChequeExportView.as_view(), name="cheque-export"),
] + router.urls
