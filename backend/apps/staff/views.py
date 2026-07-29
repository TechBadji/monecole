from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.audit import AuditedModelViewSetMixin, record
from apps.core.models import AuditLog
from apps.core.periods import label as period_label
from apps.core.views_base import TenantModelViewSet

from .models import (
    Absence,
    PayrollProfile,
    PayrollScale,
    Payslip,
    Salary,
    SalaryRaise,
    SalaryRubric,
    Teacher,
    TeacherContract,
)
from .serializers import (
    AbsenceSerializer,
    PayrollProfileSerializer,
    PayrollScaleSerializer,
    PayslipSerializer,
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


class PayrollScaleViewSet(TenantModelViewSet):
    serializer_class = PayrollScaleSerializer
    resource = "salaryrubric"
    model = PayrollScale


class PayrollProfileViewSet(TenantModelViewSet):
    serializer_class = PayrollProfileSerializer
    resource = "salary"
    model = PayrollProfile
    select_related = ("teacher",)
    filterset_fields = ["is_executive", "teacher"]


class PayslipViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    """Bulletins de paie. Générés, jamais saisis à la main."""

    serializer_class = PayslipSerializer
    resource = "salary"
    model = Payslip
    select_related = ("teacher", "scale")
    filterset_fields = ["year", "period", "teacher"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Génère les bulletins du mois pour tous les employés ayant un profil de paie.

        Idempotent : un bulletin déjà émis pour la période n'est pas recalculé. Le
        recalculer écraserait un document déjà remis au salarié — s'il faut le
        corriger, il faut le supprimer explicitement d'abord.
        """
        from datetime import date

        from apps.core.periods import end_of_month

        from .payroll import compute_payslip

        year = self.current_year()
        raw_period = request.data.get("period")
        period = end_of_month(
            date.fromisoformat(raw_period) if raw_period else date.today()
        )

        scale = PayrollScale.applicable(period)
        if scale is None:
            raise ValidationError(
                {"scale": "Aucun barème de paie défini. Créez-en un avant de générer."}
            )

        profiles = PayrollProfile.objects.select_related("teacher").filter(
            teacher__is_active=True
        )
        existing = set(
            Payslip.objects.filter(period=period).values_list("teacher_id", flat=True)
        )

        created, skipped = [], 0
        with transaction.atomic():
            for profile in profiles:
                if profile.teacher_id in existing:
                    skipped += 1
                    continue

                computation = compute_payslip(
                    scale=scale.values,
                    gross=profile.gross,
                    non_taxable=profile.non_taxable_allowance,
                    is_executive=profile.is_executive,
                    family_shares=profile.family_shares,
                )
                detail = computation.as_dict()
                created.append(
                    Payslip.objects.create(
                        school=request.user.school,
                        teacher=profile.teacher,
                        year=year,
                        scale=scale,
                        period=period,
                        gross=computation.gross,
                        non_taxable=computation.non_taxable,
                        employee_contributions=computation.total_employee,
                        employer_contributions=computation.total_employer,
                        income_tax=computation.income_tax,
                        trimf=computation.trimf,
                        other_deductions=computation.other_deductions,
                        net_pay=computation.net_pay,
                        computation=detail,
                    )
                )

        return Response(
            {
                "period": period,
                "scale": scale.label,
                "scale_validated": scale.is_validated,
                "created": len(created),
                "skipped": skipped,
                "total_net": sum(p.net_pay for p in created),
                "total_employer_cost": sum(p.employer_cost for p in created),
                "warning": None if scale.is_validated else
                    "Barème non validé par un expert-comptable — vérifiez les taux "
                    "avant de remettre ces bulletins.",
                "payslips": PayslipSerializer(created, many=True).data,
            },
            status=201,
        )

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        from .payslip_pdf import payslip_pdf

        payslip = self.get_object()
        response = payslip_pdf(payslip, request.user.school)
        filename = f"bulletin-{payslip.teacher.matricule}-{payslip.period:%Y-%m}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        record(request, AuditLog.Action.EXPORT, payslip)
        return response

    @action(detail=False, methods=["get"], url_path="pdf-batch")
    def pdf_batch(self, request):
        """Tous les bulletins d'un mois en un seul PDF, un par page."""
        from datetime import date

        from apps.core.periods import end_of_month

        from .payslip_pdf import payslips_pdf

        raw_period = request.query_params.get("period")
        if not raw_period:
            raise ValidationError({"period": "Paramètre `period` requis."})
        period = end_of_month(date.fromisoformat(raw_period))

        payslips = list(
            Payslip.objects.filter(period=period).select_related("teacher", "scale")
        )
        if not payslips:
            raise ValidationError({"period": f"Aucun bulletin pour {period:%m/%Y}."})

        response = payslips_pdf(payslips, request.user.school)
        response["Content-Disposition"] = (
            f'attachment; filename="bulletins-{period:%Y-%m}.pdf"'
        )
        record(request, AuditLog.Action.EXPORT, payslips[0])
        return response
