from django.db import transaction
from django.db.models import Count, Q, Sum
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.audit import AuditedModelViewSetMixin
from apps.core.views_base import TenantModelViewSet

from .models import (
    ClassEnrollmentHistory,
    ClassRoom,
    Discount,
    Enrollment,
    Family,
    FeeSchedule,
    MonthlyPayment,
    Student,
    StudentStatus,
)
from .serializers import (
    BulkMonthlyPaymentSerializer,
    ClassEnrollmentHistorySerializer,
    ClassRoomSerializer,
    DiscountSerializer,
    EnrollmentSerializer,
    FamilySerializer,
    FeeScheduleSerializer,
    MonthlyPaymentSerializer,
    StudentSerializer,
)


class ClassRoomViewSet(TenantModelViewSet):
    serializer_class = ClassRoomSerializer
    resource = "classroom"
    filterset_fields = ["level"]
    search_fields = ["name"]

    def get_queryset(self):
        # `order_by` explicite : le GROUP BY introduit par `annotate` fait perdre
        # l'ordre implicite du Meta, et une pagination non ordonnée renvoie des
        # doublons d'une page à l'autre.
        return ClassRoom.objects.annotate(
            student_count=Count("students", filter=Q(students__status=StudentStatus.ACTIVE))
        ).order_by("order", "name")


class FamilyViewSet(TenantModelViewSet):
    serializer_class = FamilySerializer
    resource = "family"
    model = Family
    search_fields = ["name", "primary_contact", "phone"]


class StudentViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    serializer_class = StudentSerializer
    resource = "student"
    filterset_fields = ["classroom", "status", "family", "sex"]
    search_fields = ["first_name", "last_name", "parent_name", "parent_phone"]

    def get_queryset(self):
        qs = Student.objects.select_related("classroom", "family")
        user = self.request.user
        # Un parent ne voit que ses propres enfants — le filtre est appliqué ici, pas
        # laissé au client.
        if user.role == "PARENT":
            qs = qs.filter(family__email=user.email)
        return qs

    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        """Situation financière de l'élève : dû, réglé, reste à payer.

        Le classeur source n'enregistre que les sommes reçues, ce qui ne permet pas
        de distinguer un paiement partiel d'un paiement complet. La grille tarifaire
        fournit ici le montant dû, d'où découlent le solde et le retard.
        """
        student = self.get_object()
        year = self.current_year()
        schedule = FeeSchedule.objects.filter(classroom=student.classroom, year=year).first()
        if schedule is None:
            raise ValidationError(
                {
                    "fee_schedule": f"Aucune grille tarifaire pour {student.classroom} "
                    f"en {year}. Le montant dû est indéterminable."
                }
            )

        enrollment = Enrollment.objects.filter(student=student, year=year).first()
        payments = MonthlyPayment.objects.filter(student=student, year=year).order_by("period")

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

        paid_by_period = {p.period: p for p in payments}
        lines = []
        for period in year.tuition_month_ends:
            payment = paid_by_period.get(period)
            paid = payment.tuition if payment else 0
            lines.append(
                {
                    "period": period,
                    "due": tuition_due,
                    "paid": paid,
                    "balance": tuition_due - paid,
                    "status": _payment_status(paid, tuition_due),
                    "canteen": payment.canteen if payment else 0,
                    "reinforcement": payment.reinforcement if payment else 0,
                    "uniform": payment.uniform if payment else 0,
                }
            )

        registration_paid = enrollment.registration_amount if enrollment else 0
        total_due = registration_due + tuition_due * year.tuition_months
        total_paid = registration_paid + sum(line["paid"] for line in lines)

        return Response(
            {
                "student": {"id": student.id, "name": student.full_name,
                            "classroom": student.classroom.name},
                "year": year.label,
                "registration": {
                    "due": registration_due,
                    "paid": registration_paid,
                    "balance": registration_due - registration_paid,
                    "status": _payment_status(registration_paid, registration_due),
                },
                "months": lines,
                "discounts": DiscountSerializer(discounts, many=True).data,
                "total_due": total_due,
                "total_paid": total_paid,
                "balance": total_due - total_paid,
            }
        )


def _payment_status(paid, due):
    if due == 0 or paid >= due:
        return "PAID"
    return "PARTIAL" if paid > 0 else "UNPAID"


class FeeScheduleViewSet(TenantModelViewSet):
    serializer_class = FeeScheduleSerializer
    resource = "classroom"
    model = FeeSchedule
    select_related = ("classroom", "year")
    filterset_fields = ["classroom", "year"]


class EnrollmentViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    serializer_class = EnrollmentSerializer
    resource = "enrollment"
    model = Enrollment
    select_related = ("student", "classroom", "year")
    filterset_fields = ["year", "classroom", "registration_paid"]
    search_fields = ["student__first_name", "student__last_name"]


class MonthlyPaymentViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    serializer_class = MonthlyPaymentSerializer
    resource = "monthlypayment"
    model = MonthlyPayment
    select_related = ("student", "student__classroom")
    filterset_fields = ["year", "period", "student", "method", "student__classroom"]
    search_fields = ["student__first_name", "student__last_name", "reference"]

    @action(detail=False, methods=["get"], url_path="register")
    def register(self, request):
        """Grille d'encaissement d'une classe pour un mois donné.

        Renvoie chaque élève actif de la classe avec ce qu'il a déjà réglé, prêt à
        être affiché en tableau éditable puis renvoyé en une seule fois à `bulk`.
        """
        year = self.current_year()
        classroom_id = request.query_params.get("classroom")
        period = request.query_params.get("period")
        if not classroom_id or not period:
            raise ValidationError(
                {"detail": "Les paramètres `classroom` et `period` sont requis."}
            )

        from apps.core.periods import end_of_month
        from datetime import date

        period = end_of_month(date.fromisoformat(period))
        students = Student.objects.filter(
            classroom_id=classroom_id, status=StudentStatus.ACTIVE
        ).order_by("last_name", "first_name")
        schedule = FeeSchedule.objects.filter(classroom_id=classroom_id, year=year).first()
        existing = {
            p.student_id: p
            for p in MonthlyPayment.objects.filter(
                year=year, period=period, student__classroom_id=classroom_id
            )
        }

        rows = []
        for student in students:
            payment = existing.get(student.id)
            rows.append(
                {
                    "student": student.id,
                    "name": student.full_name,
                    "tuition": payment.tuition if payment else 0,
                    "canteen": payment.canteen if payment else 0,
                    "reinforcement": payment.reinforcement if payment else 0,
                    "uniform": payment.uniform if payment else 0,
                    "method": payment.method if payment else MonthlyPayment.Method.CASH,
                    "payment_date": payment.payment_date if payment else None,
                    "recorded": payment is not None,
                }
            )

        return Response(
            {
                "year": year.label,
                "period": period,
                "expected_tuition": schedule.monthly_tuition if schedule else None,
                "expected_canteen": schedule.monthly_canteen if schedule else None,
                "rows": rows,
            }
        )

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """Enregistre en une transaction les encaissements d'une classe.

        Tout ou rien : un lot partiellement appliqué laisserait la caisse dans un
        état que le comptable ne pourrait pas rapprocher.
        """
        serializer = BulkMonthlyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year = self.current_year()
        period = serializer.validated_data["period"]
        entries = serializer.validated_data["entries"]

        student_ids = [e.get("student") for e in entries]
        known = set(
            Student.objects.filter(id__in=student_ids).values_list("id", flat=True)
        )
        unknown = [s for s in student_ids if s not in known]
        if unknown:
            raise ValidationError(
                {"entries": f"Élèves inconnus dans cet établissement : {unknown}"}
            )

        saved = []
        with transaction.atomic():
            for entry in entries:
                payment, _ = MonthlyPayment.objects.update_or_create(
                    student_id=entry["student"],
                    period=period,
                    defaults={
                        "school": request.user.school,
                        "year": year,
                        "tuition": int(entry.get("tuition") or 0),
                        "canteen": int(entry.get("canteen") or 0),
                        "reinforcement": int(entry.get("reinforcement") or 0),
                        "uniform": int(entry.get("uniform") or 0),
                        "payment_date": entry.get("payment_date") or None,
                        "method": entry.get("method") or MonthlyPayment.Method.CASH,
                        "reference": entry.get("reference") or "",
                        "received_by": request.user.get_full_name() or request.user.email,
                    },
                )
                saved.append(payment)

        from apps.core.audit import record
        from apps.core.models import AuditLog

        for payment in saved:
            record(request, AuditLog.Action.CREATE, payment)

        return Response(
            {"saved": len(saved), "period": period, "total": sum(p.total for p in saved)}
        )

    @action(detail=False, methods=["get"])
    def arrears(self, request):
        """Élèves en retard de paiement, tous mois échus confondus."""
        year = self.current_year()
        schedules = {
            s.classroom_id: s for s in FeeSchedule.objects.filter(year=year)
        }
        paid = {
            row["student"]: row["total"]
            for row in MonthlyPayment.objects.filter(year=year)
            .values("student")
            .annotate(total=Sum("tuition"))
        }

        from datetime import date

        today = date.today()
        elapsed = [p for p in year.tuition_month_ends if p <= today]

        results = []
        for student in Student.objects.filter(status=StudentStatus.ACTIVE).select_related(
            "classroom"
        ):
            schedule = schedules.get(student.classroom_id)
            if schedule is None:
                continue
            due = schedule.monthly_tuition * len(elapsed)
            settled = paid.get(student.id, 0)
            if settled < due:
                results.append(
                    {
                        "student": student.id,
                        "name": student.full_name,
                        "classroom": student.classroom.name,
                        "parent_phone": student.parent_phone,
                        "due": due,
                        "paid": settled,
                        "arrears": due - settled,
                        "months_elapsed": len(elapsed),
                    }
                )

        results.sort(key=lambda r: r["arrears"], reverse=True)
        return Response({"year": year.label, "count": len(results), "results": results})


class DiscountViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    serializer_class = DiscountSerializer
    resource = "discount"
    model = Discount
    select_related = ("student", "family")
    filterset_fields = ["year", "kind", "student", "family"]


class ClassEnrollmentHistoryViewSet(TenantModelViewSet):
    serializer_class = ClassEnrollmentHistorySerializer
    resource = "student"
    model = ClassEnrollmentHistory
    select_related = ("student", "to_classroom")
    filterset_fields = ["student", "year"]
