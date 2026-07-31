from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .account import (
    PasswordChangeView,
    PasswordResetCheckView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfilePhotoView,
    ProfileView,
    SessionListView,
    SessionRevokeView,
)
from .import_views import DataImportView, ImportTemplateView
from .workbook_views import WorkbookImportView
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
    path("auth/me/profile/", ProfileView.as_view(), name="profile"),
    path("auth/me/photo/", ProfilePhotoView.as_view(), name="profile-photo"),
    path("auth/me/password/", PasswordChangeView.as_view(), name="password-change"),
    path("auth/sessions/", SessionListView.as_view(), name="sessions"),
    path("auth/sessions/<int:pk>/", SessionRevokeView.as_view(), name="session-revoke"),
    path(
        "auth/password-reset/",
        PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "auth/password-reset/check/",
        PasswordResetCheckView.as_view(),
        name="password-reset-check",
    ),
    path(
        "auth/password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("imports/", DataImportView.as_view(), name="data-import"),
    path("imports/workbook/", WorkbookImportView.as_view(), name="workbook-import"),
    path(
        "imports/template/<str:kind>.csv",
        ImportTemplateView.as_view(),
        name="import-template",
    ),
    path("", include(router.urls)),
]
