from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AbsenceViewSet,
    SalaryRaiseViewSet,
    SalaryRubricViewSet,
    SalaryViewSet,
    TeacherContractViewSet,
    TeacherViewSet,
)

router = DefaultRouter()
router.register("teachers", TeacherViewSet, basename="teacher")
router.register("teacher-contracts", TeacherContractViewSet, basename="teachercontract")
router.register("absences", AbsenceViewSet, basename="absence")
router.register("salary-rubrics", SalaryRubricViewSet, basename="salaryrubric")
router.register("salaries", SalaryViewSet, basename="salary")
router.register("salary-raises", SalaryRaiseViewSet, basename="salaryraise")

urlpatterns = [path("", include(router.urls))]
