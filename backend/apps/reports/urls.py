from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ReportExportView, ReportViewSet

router = DefaultRouter()
router.register("reports", ReportViewSet, basename="report")

urlpatterns = router.urls + [
    path(
        "exports/<str:report>.<str:fmt>",
        ReportExportView.as_view(),
        name="report-export",
    ),
]
