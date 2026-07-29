from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.audit import AuditedModelViewSetMixin
from apps.core.models import Role
from apps.core.views_base import TenantModelViewSet

from .models import Expense, ExpenseCategory, OtherIncome, RecurringExpense
from .serializers import (
    ExpenseCategorySerializer,
    ExpenseSerializer,
    OtherIncomeSerializer,
    RecurringExpenseSerializer,
)

# Au-delà de ce montant, une dépense saisie par un comptable part en validation
# plutôt que d'entrer directement au bilan.
APPROVAL_THRESHOLD = 500_000


class ExpenseCategoryViewSet(TenantModelViewSet):
    serializer_class = ExpenseCategorySerializer
    resource = "expensecategory"
    model = ExpenseCategory
    filterset_fields = ["is_active"]


class ExpenseViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    serializer_class = ExpenseSerializer
    resource = "expense"
    model = Expense
    select_related = ("category", "year")
    filterset_fields = ["year", "period", "category", "channel", "status"]
    search_fields = ["label", "invoice_number"]

    def perform_create(self, serializer):
        user = self.request.user
        amount = serializer.validated_data.get("amount", 0)
        # Séparation des tâches : au-delà du seuil, le comptable saisit mais ne
        # valide pas. L'administrateur reste seul à pouvoir engager le bilan.
        if amount >= APPROVAL_THRESHOLD and user.role == Role.ACCOUNTANT:
            serializer.validated_data["status"] = Expense.Status.PENDING
        super().perform_create(serializer)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Valide une dépense en attente. Réservé à l'administrateur."""
        if request.user.role != Role.ADMIN:
            raise PermissionDenied("Seul un administrateur peut valider une dépense.")
        expense = self.get_object()
        if expense.status != Expense.Status.PENDING:
            raise ValidationError(
                {"status": f"Dépense déjà « {expense.get_status_display()} »."}
            )
        expense.status = Expense.Status.APPROVED
        expense.approved_by = request.user.get_full_name() or request.user.email
        expense.approved_at = timezone.now()
        expense.save()

        from apps.core.audit import record
        from apps.core.models import AuditLog

        record(request, AuditLog.Action.UPDATE, expense)
        return Response(self.get_serializer(expense).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Répartition des dépenses par rubrique sur l'exercice."""
        year = self.current_year()
        rows = (
            Expense.objects.filter(year=year, status=Expense.Status.APPROVED)
            .values("category", "category__label")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")
        )
        total = sum(r["total"] or 0 for r in rows)
        return Response(
            {
                "year": year.label,
                "total": total,
                "categories": [
                    {
                        "category": r["category"],
                        "label": r["category__label"],
                        "total": r["total"] or 0,
                        "count": r["count"],
                        "share": round((r["total"] or 0) / total, 4) if total else 0,
                    }
                    for r in rows
                ],
            }
        )


class RecurringExpenseViewSet(TenantModelViewSet):
    serializer_class = RecurringExpenseSerializer
    resource = "expense"
    model = RecurringExpense
    select_related = ("category",)

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Crée les brouillons du mois à partir des récurrences actives.

        Idempotent : une récurrence déjà matérialisée sur la période n'est pas
        dupliquée, ce qui rend l'appel rejouable sans risque.
        """
        from datetime import date

        from apps.core.periods import end_of_month

        year = self.current_year()
        target = request.data.get("period")
        target = date.fromisoformat(target) if target else date.today()
        period = end_of_month(target)

        created = []
        with transaction.atomic():
            for template in RecurringExpense.objects.filter(is_active=True):
                if template.start_date > period:
                    continue
                if template.end_date and template.end_date < period.replace(day=1):
                    continue
                if Expense.objects.filter(recurring_template=template, period=period).exists():
                    continue
                day = min(template.day_of_month, period.day)
                created.append(
                    Expense.objects.create(
                        school=request.user.school,
                        year=year,
                        operation_date=period.replace(day=day),
                        label=template.label,
                        amount=template.amount,
                        channel=template.channel,
                        category=template.category,
                        status=Expense.Status.DRAFT,
                        recurring_template=template,
                    )
                )

        return Response(
            {"period": period, "created": len(created),
             "expenses": ExpenseSerializer(created, many=True).data}
        )


class OtherIncomeViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    serializer_class = OtherIncomeSerializer
    resource = "expense"
    model = OtherIncome
    select_related = ("year",)
    filterset_fields = ["year", "period"]
    search_fields = ["label", "reference"]
