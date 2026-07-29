from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ClassEnrollmentHistoryViewSet,
    ClassRoomViewSet,
    DiscountViewSet,
    EnrollmentViewSet,
    FamilyViewSet,
    FeeScheduleViewSet,
    MonthlyPaymentViewSet,
    StudentViewSet,
)

router = DefaultRouter()
router.register("classes", ClassRoomViewSet, basename="classroom")
router.register("families", FamilyViewSet, basename="family")
router.register("students", StudentViewSet, basename="student")
router.register("fee-schedules", FeeScheduleViewSet, basename="feeschedule")
router.register("enrollments", EnrollmentViewSet, basename="enrollment")
router.register("monthly-payments", MonthlyPaymentViewSet, basename="monthlypayment")
router.register("discounts", DiscountViewSet, basename="discount")
router.register("class-history", ClassEnrollmentHistoryViewSet, basename="classhistory")

urlpatterns = [path("", include(router.urls))]
