from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ClassSubjectApplyCatalogueView,
    ClassSubjectBulkView,
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

# Les chemins explicites précèdent le routeur : sinon « apply-catalogue » et
# « bulk » sont happés par la route de détail du ViewSet, qui les prend pour des
# identifiants et répond 405.
urlpatterns = [
    path(
        "class-subjects/apply-catalogue/",
        ClassSubjectApplyCatalogueView.as_view(),
        name="class-subjects-apply-catalogue",
    ),
    path(
        "class-subjects/bulk/",
        ClassSubjectBulkView.as_view(),
        name="class-subjects-bulk",
    ),
    path(
        "report-card-settings/",
        ReportCardSettingsView.as_view(),
        name="report-card-settings",
    ),
    path("", include(router.urls)),
]
