from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ClassSubjectViewSet,
    CompositionViewSet,
    GradeEntryViewSet,
    ReportCardSettingsView,
    ReportCardViewSet,
    SubjectViewSet,
)

router = DefaultRouter()
router.register("subjects", SubjectViewSet, basename="subject")
router.register("class-subjects", ClassSubjectViewSet, basename="classsubject")
router.register("compositions", CompositionViewSet, basename="composition")
router.register("grade-sheets", GradeEntryViewSet, basename="gradesheet")
router.register("report-cards", ReportCardViewSet, basename="reportcard")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "report-card-settings/",
        ReportCardSettingsView.as_view(),
        name="report-card-settings",
    ),
]
