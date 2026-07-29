from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.students.portal import ParentChildrenView, ParentLedgerView, ParentPaymentsView

from .views import (
    NotificationOutboxView,
    ParentOtpRequestView,
    ParentOtpVerifyView,
    ReminderViewSet,
)

router = DefaultRouter()
router.register("reminders", ReminderViewSet, basename="reminder")

urlpatterns = [
    # Authentification du portail parent — publique, limitée en débit.
    path("portal/auth/request-code/", ParentOtpRequestView.as_view(), name="parent-otp-request"),
    path("portal/auth/verify-code/", ParentOtpVerifyView.as_view(), name="parent-otp-verify"),
    # Portail parent — lecture seule sur ses propres enfants.
    path("portal/children/", ParentChildrenView.as_view(), name="parent-children"),
    path("portal/children/<int:pk>/ledger/", ParentLedgerView.as_view(), name="parent-ledger"),
    path("portal/children/<int:pk>/payments/", ParentPaymentsView.as_view(), name="parent-payments"),
    path("notifications/outbox/", NotificationOutboxView.as_view(), name="notification-outbox"),
    path("", include(router.urls)),
]
