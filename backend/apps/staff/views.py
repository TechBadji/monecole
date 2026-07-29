from django.db.models import Sum
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.audit import AuditedModelViewSetMixin
from apps.core.periods import label as period_label
from apps.core.views_base import TenantModelViewSet

from .models import Absence, Salary, SalaryRaise, SalaryRubric, Teacher, TeacherContract
from .serializers import (
    AbsenceSerializer,
    SalaryRaiseSerializer,
    SalaryRubricSerializer,
    SalarySerializer,
    TeacherContractSerializer,
    TeacherSerializer,
)


class TeacherViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    serializer_class = TeacherSerializer
    resource = "teacher"
    model = Teacher
    filterset_fields = ["is_active", "contract_type", "sex"]
    search_fields = ["first_name", "last_name", "matricule", "specialty"]


class TeacherContractViewSet(TenantModelViewSet):
    serializer_class = TeacherContractSerializer
    resource = "teacher"
    model = TeacherContract
    select_related = ("teacher",)
    filterset_fields = ["teacher", "contract_type"]


class AbsenceViewSet(TenantModelViewSet):
    serializer_class = AbsenceSerializer
    resource = "teacher"
    model = Absence
    select_related = ("teacher",)
    filterset_fields = ["teacher", "kind"]


class SalaryRubricViewSet(TenantModelViewSet):
    serializer_class = SalaryRubricSerializer
    resource = "salaryrubric"
    model = SalaryRubric
    select_related = ("teacher",)


class SalaryViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    serializer_class = SalarySerializer
    resource = "salary"
    model = Salary
    select_related = ("rubric", "rubric__teacher")
    filterset_fields = ["year", "period", "rubric"]

    @action(detail=False, methods=["get"])
    def grid(self, request):
        """Grille rubriques × mois — équivalent de l'onglet « Salaires ».

        Le total annuel couvre les 12 mois de l'exercice, septembre compris : la
        formule d'origine (`SUM(F7:P7)`) s'arrêtait à août.
        """
        year = self.current_year()
        periods = year.fiscal_months
        rubrics = list(SalaryRubric.objects.order_by("order", "code"))

        amounts = {(r.id, p): 0 for r in rubrics for p in periods}
        for entry in Salary.objects.filter(year=year).values("rubric", "period").annotate(
            total=Sum("gross_amount")
        ):
            key = (entry["rubric"], entry["period"])
            if key in amounts:
                amounts[key] = entry["total"] or 0

        rows = [
            {
                "rubric": r.id,
                "code": r.code,
                "label": r.label,
                "teacher": r.teacher.full_name if r.teacher else None,
                "values": [amounts[(r.id, p)] for p in periods],
                "total": sum(amounts[(r.id, p)] for p in periods),
            }
            for r in rubrics
        ]
        totals = [sum(amounts[(r.id, p)] for r in rubrics) for p in periods]

        return Response(
            {
                "year": year.label,
                "periods": [{"date": p, "label": period_label(p)} for p in periods],
                "rows": rows,
                "personnel_charges": {"values": totals, "total": sum(totals)},
            }
        )


class SalaryRaiseViewSet(TenantModelViewSet):
    serializer_class = SalaryRaiseSerializer
    resource = "salary"
    model = SalaryRaise
    select_related = ("teacher",)
    filterset_fields = ["teacher"]
