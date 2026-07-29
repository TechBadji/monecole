"""Portail parent — lecture seule sur ses propres enfants.

Le périmètre n'est jamais dérivé d'un identifiant fourni par le client : il découle
du numéro de téléphone porté par le compte, rapproché des fiches élèves. Un parent
qui manipulerait un identifiant d'élève dans l'URL ne verrait rien de plus.
"""

from django.db.models import Q, Sum
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Role
from apps.core.views_base import TenantViewSetMixin

from .models import Discount, Enrollment, FeeSchedule, MonthlyPayment, Student, StudentStatus


class ParentScopedMixin(TenantViewSetMixin):
    resource = "student"

    def my_children(self):
        user = self.request.user
        if user.role != Role.PARENT:
            raise PermissionDenied("Réservé au portail parent.")
        phone = user.phone
        if not phone:
            return Student.objects.none()
        return (
            Student.objects.filter(status=StudentStatus.ACTIVE)
            .filter(Q(parent_phone_e164=phone) | Q(family__phone_e164=phone))
            .select_related("classroom", "family")
            .distinct()
        )

    def get_child(self, pk):
        child = self.my_children().filter(pk=pk).first()
        if child is None:
            # 404 plutôt que 403 : confirmer l'existence d'un élève qu'on n'a pas le
            # droit de voir est déjà une fuite.
            raise NotFound("Élève introuvable.")
        return child


def student_ledger(student, year):
    """Situation financière d'un élève : dû, réglé, reste à payer, par échéance."""
    schedule = FeeSchedule.objects.filter(classroom=student.classroom, year=year).first()
    if schedule is None:
        return None

    discounts = Discount.objects.filter(year=year).filter(
        Q(student=student) | Q(family=student.family_id)
    )
    tuition_due = schedule.monthly_tuition
    registration_due = schedule.registration_fee
    for discount in discounts:
        if discount.scope in (Discount.Scope.TUITION, Discount.Scope.BOTH):
            tuition_due = discount.apply_to(tuition_due)
        if discount.scope in (Discount.Scope.REGISTRATION, Discount.Scope.BOTH):
            registration_due = discount.apply_to(registration_due)

    enrollment = Enrollment.objects.filter(student=student, year=year).first()
    payments = {
        p.period: p
        for p in MonthlyPayment.objects.filter(student=student, year=year)
    }

    months = []
    for period in year.tuition_month_ends:
        payment = payments.get(period)
        paid = payment.tuition if payment else 0
        months.append(
            {
                "period": period,
                "due": tuition_due,
                "paid": paid,
                "balance": max(0, tuition_due - paid),
                "status": "PAID" if paid >= tuition_due else ("PARTIAL" if paid else "UNPAID"),
                "canteen": payment.canteen if payment else 0,
                "reinforcement": payment.reinforcement if payment else 0,
                "paid_at": payment.payment_date if payment else None,
                "method": payment.method if payment else None,
            }
        )

    registration_paid = enrollment.registration_amount if enrollment else 0
    total_due = registration_due + tuition_due * year.tuition_months
    total_paid = registration_paid + sum(m["paid"] for m in months)

    return {
        "student": {
            "id": student.id,
            "name": student.full_name,
            "classroom": student.classroom.name,
        },
        "year": year.label,
        "registration": {
            "due": registration_due,
            "paid": registration_paid,
            "balance": max(0, registration_due - registration_paid),
            "status": "PAID" if registration_paid >= registration_due else (
                "PARTIAL" if registration_paid else "UNPAID"
            ),
        },
        "months": months,
        "discounts": [
            {
                "kind": d.get_kind_display(),
                "scope": d.get_scope_display(),
                "value": d.value,
                "reason": d.reason,
            }
            for d in discounts
        ],
        "total_due": total_due,
        "total_paid": total_paid,
        "balance": max(0, total_due - total_paid),
        # Ce qui reste dû sur les mois déjà échus — c'est le montant réellement
        # exigible aujourd'hui, à ne pas confondre avec le total de l'année.
        "due_now": _due_now(months, registration_due, registration_paid),
    }


def _due_now(months, registration_due, registration_paid):
    from datetime import date

    today = date.today()
    overdue = sum(m["balance"] for m in months if m["period"] <= today)
    return overdue + max(0, registration_due - registration_paid)


class ParentChildrenView(ParentScopedMixin, APIView):
    """Liste des enfants du parent connecté, avec leur solde."""

    def get(self, request):
        year = self.current_year()
        children = []
        for child in self.my_children():
            ledger = student_ledger(child, year)
            children.append(
                {
                    "id": child.id,
                    "name": child.full_name,
                    "classroom": child.classroom.name,
                    "status": child.get_status_display(),
                    "balance": ledger["balance"] if ledger else None,
                    "due_now": ledger["due_now"] if ledger else None,
                    "tariff_missing": ledger is None,
                }
            )
        return Response({"year": year.label, "children": children})


class ParentLedgerView(ParentScopedMixin, APIView):
    """Détail des échéances d'un enfant."""

    def get(self, request, pk):
        child = self.get_child(pk)
        year = self.current_year()
        ledger = student_ledger(child, year)
        if ledger is None:
            return Response(
                {
                    "detail": "Les tarifs de cette classe ne sont pas encore publiés. "
                    "Rapprochez-vous du secrétariat."
                },
                status=409,
            )
        return Response(ledger)


class ParentPaymentsView(ParentScopedMixin, APIView):
    """Historique des règlements — sert de relevé au parent."""

    def get(self, request, pk):
        child = self.get_child(pk)
        year = self.current_year()

        payments = MonthlyPayment.objects.filter(student=child, year=year).order_by("-period")
        enrollment = Enrollment.objects.filter(student=child, year=year).first()

        entries = []
        if enrollment and enrollment.registration_amount:
            entries.append(
                {
                    "kind": "REGISTRATION",
                    "label": "Frais d'inscription",
                    "amount": enrollment.registration_amount,
                    "date": enrollment.paid_at,
                    "reference": f"INS{enrollment.id}",
                    "method": None,
                }
            )
        for payment in payments:
            entries.append(
                {
                    "kind": "TUITION",
                    "label": f"Scolarité {payment.period:%m/%Y}",
                    "amount": payment.total,
                    "date": payment.payment_date,
                    "reference": payment.reference or f"MP{payment.id}",
                    "method": payment.get_method_display(),
                    "detail": {
                        "tuition": payment.tuition,
                        "canteen": payment.canteen,
                        "reinforcement": payment.reinforcement,
                        "uniform": payment.uniform,
                    },
                }
            )

        return Response(
            {
                "student": {"id": child.id, "name": child.full_name},
                "year": year.label,
                "total": sum(e["amount"] for e in entries),
                "entries": entries,
            }
        )
