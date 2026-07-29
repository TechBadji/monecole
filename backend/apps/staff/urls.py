from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AbsenceViewSet,
    PayrollProfileViewSet,
    PayrollScaleViewSet,
    PayslipViewSet,
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
router.register("payroll-scales", PayrollScaleViewSet, basename="payrollscale")
router.register("payroll-profiles", PayrollProfileViewSet, basename="payrollprofile")
router.register("payslips", PayslipViewSet, basename="payslip")

urlpatterns = [path("", include(router.urls))]
