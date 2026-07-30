from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AttendanceViewSet, QrSheetView, ScanViewSet

router = DefaultRouter()
router.register("attendance", AttendanceViewSet, basename="attendance")
router.register("scan", ScanViewSet, basename="scan")

urlpatterns = [
    path("", include(router.urls)),
    path("qr-sheet/", QrSheetView.as_view(), name="qr-sheet"),
]
