from datetime import date

from django.db.models import Sum
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from apps.core.audit import record
from apps.core.models import AuditLog, SchoolYear
from apps.core.periods import label as period_label
from apps.core.views_base import TenantViewSetMixin
from apps.finance.models import Expense
from apps.students.models import MonthlyPayment, Student, StudentStatus

from . import exports
from .services import bilan, comparison, encaissements, scholarships


class ReportViewSet(TenantViewSetMixin, ViewSet):
    """États financiers. Lecture seule — tout est calculé à la demande."""

    resource = "report"

    def list(self, request):
        return Response(
            {
                "available": [
                    {"key": "encais", "label": "Synthèse des encaissements"},
                    {"key": "bilan", "label": "Rapport bilan"},
                    {"key": "comparison", "label": "Comparatif N / N-1"},
                    {"key": "dashboard", "label": "Tableau de bord"},
                    {"key": "cash-forecast", "label": "Trésorerie prévisionnelle"},
                    {"key": "scholarships", "label": "Bourses accordées"},
                ]
            }
        )

    def retrieve(self, request, pk=None):
        year = self.current_year()
        if pk == "encais":
            return Response(encaissements(year))
        if pk == "bilan":
            return Response(bilan(year))
        if pk == "comparison":
            previous = (
                SchoolYear.objects.filter(start_date__lt=year.start_date)
                .order_by("-start_date")
                .first()
            )
            return Response(comparison(year, previous))
        if pk == "dashboard":
            return Response(self._dashboard(year))
        if pk == "cash-forecast":
            return Response(self._cash_forecast(year))
        if pk == "scholarships":
            return Response(scholarships(year))
        return Response({"detail": f"Rapport « {pk} » inconnu."}, status=404)

    # ------------------------------------------------------------------ #

    def _dashboard(self, year):
        report = bilan(year)
        periods = year.fiscal_months
        today = date.today()
        elapsed = [p for p in periods if p <= today] or periods[:1]

        expenses_by_category = list(
            Expense.objects.filter(year=year, status=Expense.Status.APPROVED)
            .values("category__label")
            .annotate(total=Sum("amount"))
            .order_by("-total")[:10]
        )

        # Alerte de dépassement : rubriques dont le réalisé excède le budget cumulé
        # sur les mois écoulés.
        overruns = []
        for row in report["charges"]:
            budget = None
            from apps.finance.models import ExpenseCategory

            category = ExpenseCategory.objects.filter(code=row["key"]).first()
            if category and category.monthly_budget:
                budget = category.monthly_budget * len(elapsed)
                if row["total"] > budget:
                    overruns.append(
                        {
                            "category": row["label"],
                            "budget": budget,
                            "actual": row["total"],
                            "overrun": row["total"] - budget,
                        }
                    )

        return {
            "year": year.label,
            "headcount": report["headcount_total"],
            # Visibilité demandée par l'administration : ce que les bourses coûtent.
            "scholarships": {
                "beneficiaries": report["scholarships"]["beneficiaries"],
                "full_scholarships": report["scholarships"]["full_scholarships"],
                "forgone": report["scholarships"]["total_forgone"],
                "effort_rate": report["scholarships"]["effort_rate"],
            },
            "revenue": report["total_resources"]["total"],
            "charges": report["total_charges"]["total"],
            "ebe": report["ebe"]["total"],
            "current_balance": report["current_balance"],
            "monthly": {
                "periods": [period_label(p) for p in periods],
                "resources": report["total_resources"]["values"],
                "charges": report["total_charges"]["values"],
                "cumulative_balance": report["cumulative_balance"]["values"],
            },
            "top_expenses": [
                {"label": e["category__label"], "total": e["total"]} for e in expenses_by_category
            ],
            "revenue_by_class": report["headcount_by_class"],
            "budget_overruns": overruns,
        }

    def _cash_forecast(self, year):
        """Projection des mensualités restant à encaisser sur l'année.

        Hypothèse explicite : le taux de recouvrement observé sur les mois écoulés
        se maintient. C'est une projection, pas un engagement — la restituer sans
        afficher l'hypothèse conduirait à la lire comme une certitude.
        """
        from apps.students.models import FeeSchedule

        today = date.today()
        tuition_periods = year.tuition_month_ends
        elapsed = [p for p in tuition_periods if p <= today]
        remaining = [p for p in tuition_periods if p > today]

        schedules = {s.classroom_id: s.monthly_tuition for s in FeeSchedule.objects.filter(year=year)}
        headcount = {}
        for student in Student.objects.filter(status=StudentStatus.ACTIVE).only("classroom_id"):
            headcount[student.classroom_id] = headcount.get(student.classroom_id, 0) + 1

        expected_monthly = sum(
            schedules.get(cid, 0) * count for cid, count in headcount.items()
        )
        collected = (
            MonthlyPayment.objects.filter(year=year, period__in=elapsed).aggregate(
                total=Sum("tuition")
            )["total"]
            or 0
        )
        expected_to_date = expected_monthly * len(elapsed)
        rate = (collected / expected_to_date) if expected_to_date else 0

        return {
            "year": year.label,
            "expected_monthly": expected_monthly,
            "months_elapsed": len(elapsed),
            "months_remaining": len(remaining),
            "collected_to_date": collected,
            "expected_to_date": expected_to_date,
            "collection_rate": round(rate, 4),
            "assumption": "Projection au taux de recouvrement constaté sur les mois écoulés.",
            "forecast": [
                {
                    "period": p,
                    "label": period_label(p),
                    "expected": expected_monthly,
                    "projected": round(expected_monthly * rate),
                }
                for p in remaining
            ],
            "projected_year_end": collected + round(expected_monthly * rate * len(remaining)),
        }


class ReportExportView(TenantViewSetMixin, APIView):
    """Export d'un état en Excel ou PDF."""

    resource = "report"

    def get(self, request, report, fmt):
        year = self.current_year()
        builders = {
            ("encais", "xlsx"): (exports.encais_xlsx, "encaissements"),
            ("bilan", "xlsx"): (exports.bilan_xlsx, "rapport-bilan"),
            ("bilan", "pdf"): (exports.bilan_pdf, "rapport-bilan"),
            ("students", "xlsx"): (exports.students_xlsx, "liste-eleves"),
        }
        builder = builders.get((report, fmt))
        if builder is None:
            return Response(
                {"detail": f"Export « {report}.{fmt} » non disponible."}, status=404
            )

        build, basename = builder
        response = build(year, request)
        record(request, AuditLog.Action.EXPORT, year)
        filename = f"{basename}-{year.label.replace('/', '-')}.{fmt}"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
