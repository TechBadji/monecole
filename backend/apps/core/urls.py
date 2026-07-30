from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .import_views import DataImportView, ImportTemplateView
from .views import (
    AuditLogViewSet,
    LoginView,
    MeView,
    NotificationViewSet,
    SchoolViewSet,
    SchoolYearViewSet,
    SubscriptionViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("schools", SchoolViewSet, basename="school")
router.register("subscriptions", SubscriptionViewSet, basename="subscription")
router.register("school-years", SchoolYearViewSet, basename="schoolyear")
router.register("users", UserViewSet, basename="user")
router.register("audit-logs", AuditLogViewSet, basename="auditlog")
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("imports/", DataImportView.as_view(), name="data-import"),
    path(
        "imports/template/<str:kind>.csv",
        ImportTemplateView.as_view(),
        name="import-template",
    ),
    path("", include(router.urls)),
]
