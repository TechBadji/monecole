from django.db import transaction
from django.db.models import Count, Q, Sum
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.audit import AuditedModelViewSetMixin
from apps.core.models import Role
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

    def destroy(self, request, *args, **kwargs):
        """Refuse de supprimer une classe qui porte encore des élèves.

        La clé étrangère est en `PROTECT`, donc la base s'y oppose déjà — mais
        l'exception remonterait en 500 illisible. Ici, l'administrateur apprend
        combien d'élèves déplacer d'abord.
        """
        instance = self.get_object()
        count = instance.students.count()
        if count:
            raise ValidationError(
                {
                    "detail": (
                        f"« {instance.name} » compte encore {count} élève(s). "
                        "Transférez-les dans une autre classe avant de la "
                        "supprimer."
                    )
                }
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="grades")
    def grades(self, request):
        """Niveaux disponibles et sections déjà créées pour chacun."""
        from .grades import GRADES, grade_rank

        existing = list(ClassRoom.objects.all())
        by_rank: dict[int, list] = {}
        for classroom in existing:
            by_rank.setdefault(grade_rank(classroom.name), []).append(classroom.name)

        return Response(
            [
                {
                    "code": code,
                    "label": label,
                    "level": level,
                    "sections": sorted(by_rank.get(rank, [])),
                }
                for rank, (code, label, level) in enumerate(GRADES)
            ]
        )

    @action(detail=False, methods=["post"], url_path="sections")
    def sections(self, request):
        """Crée les sections d'un même niveau : CI-A, CI-B, CI-C…

        Une école à deux classes de CI ne doit pas avoir à saisir chaque classe
        et à deviner son rang d'affichage.

        Si une classe porte le nom nu du niveau — « CI » — elle est **renommée**
        en « CI-A » plutôt que doublée : garder « CI » à côté de « CI-A » et
        « CI-B » laisserait une classe sans section, et ses élèves avec elle.
        Le renommage préserve l'identifiant, donc les élèves, les tarifs et les
        notes déjà rattachés.
        """
        from .grades import display_order, level_of, section_name, SECTION_LETTERS

        if request.user.role != Role.ADMIN:
            raise PermissionDenied("Seul un administrateur crée des classes.")

        code = (request.data.get("grade") or "").strip().upper()
        level = level_of(code)
        if level is None:
            raise ValidationError({"grade": f"Niveau inconnu : « {code} »."})

        try:
            count = int(request.data.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        if not 1 <= count <= len(SECTION_LETTERS):
            raise ValidationError(
                {"count": f"Indiquez un nombre de sections entre 1 et {len(SECTION_LETTERS)}."}
            )

        capacity = request.data.get("capacity") or None
        created, renamed = [], None

        with transaction.atomic():
            bare = ClassRoom.objects.filter(name__iexact=code).first()
            for index in range(count):
                name = section_name(code, index)
                order = display_order(code, index)

                if bare is not None and index == 0:
                    bare.name = name
                    bare.order = order
                    bare.level = level
                    bare.save(update_fields=["name", "order", "level"])
                    renamed = name
                    continue

                if ClassRoom.objects.filter(name__iexact=name).exists():
                    continue

                created.append(
                    ClassRoom.objects.create(
                        school=request.user.school,
                        name=name,
                        level=level,
                        order=order,
                        capacity=capacity or None,
                    )
                )

        parts = []
        if renamed:
            parts.append(f"« {code} » a été renommée « {renamed} »")
        if created:
            parts.append(f"{len(created)} classe(s) créée(s)")
        if not parts:
            parts.append("Ces sections existaient déjà")

        return Response(
            {
                "created": len(created),
                "renamed": renamed,
                "detail": ". ".join(parts) + ".",
                # `student_count` vient d'une annotation : sans elle, le
                # sérialiseur renvoie la classe amputée du champ.
                "classes": ClassRoomSerializer(
                    ClassRoom.objects.filter(name__istartswith=code)
                    .annotate(
                        student_count=Count(
                            "students", filter=Q(students__status=StudentStatus.ACTIVE)
                        )
                    )
                    .order_by("order", "name"),
                    many=True,
                ).data,
            },
            status=201,
        )

    def get_queryset(self):
        # `order_by` explicite : le GROUP BY introduit par `annotate` fait perdre
        # l'ordre implicite du Meta, et une pagination non ordonnée renvoie des
        # doublons d'une page à l'autre.
        return ClassRoom.objects.select_related("teacher").annotate(
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
    search_fields = [
        "matricule", "first_name", "last_name", "parent_name", "parent_phone",
    ]

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
        """Situation financière de l'élève pour une année : dû, réglé, reste à payer.

        `?year=<id>` permet de consulter un exercice antérieur — la situation
        passée d'un élève reste consultable tout au long de son cursus.
        """
        from .fees import due_for

        student = self.get_object()
        year = self.current_year()
        due = due_for(student, year)
        if due is None:
            raise ValidationError(
                {
                    "fee_schedule": f"Aucune grille tarifaire pour {student.classroom} "
                    f"en {year}. Le montant dû est indéterminable."
                }
            )

        enrollment = Enrollment.objects.filter(student=student, year=year).first()
        payments = {
            p.period: p
            for p in MonthlyPayment.objects.filter(student=student, year=year)
        }

        lines = []
        for period in year.tuition_month_ends:
            payment = payments.get(period)
            paid = payment.tuition if payment else 0
            lines.append(
                {
                    "period": period,
                    "due": due.monthly_tuition,
                    "paid": paid,
                    "balance": max(0, due.monthly_tuition - paid),
                    "status": _payment_status(paid, due.monthly_tuition),
                    "canteen": payment.canteen if payment else 0,
                    "reinforcement": payment.reinforcement if payment else 0,
                    "uniform": payment.uniform if payment else 0,
                }
            )

        registration_paid = enrollment.registration_amount if enrollment else 0
        total_due = due.registration + due.monthly_tuition * year.tuition_months
        total_paid = registration_paid + sum(line["paid"] for line in lines)

        return Response(
            {
                "student": {
                    "id": student.id,
                    "matricule": student.matricule,
                    "name": student.full_name,
                    "classroom": student.classroom.name,
                },
                "year": year.label,
                "year_id": year.id,
                "registration": {
                    "due": due.registration,
                    "paid": registration_paid,
                    "balance": max(0, due.registration - registration_paid),
                    "status": _payment_status(registration_paid, due.registration),
                },
                "months": lines,
                "discounts": DiscountSerializer(due.discounts, many=True).data,
                "scholarship": {
                    "rate": due.scholarship_rate,
                    "is_full": due.is_full_scholarship,
                    "forgone": due.forgone(year.tuition_months),
                    "full_monthly_tuition": due.full_monthly_tuition,
                },
                "total_due": total_due,
                "total_paid": total_paid,
                "balance": max(0, total_due - total_paid),
            }
        )

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Situation financière année par année, sur tout le cursus de l'élève.

        Une année sans grille tarifaire est retournée avec `available` à faux
        plutôt qu'omise : l'absence de tarif est une information, pas un trou.
        """
        from apps.core.models import SchoolYear

        from .fees import due_for

        student = self.get_object()
        years = SchoolYear.objects.order_by("-start_date")

        entries = []
        for year in years:
            due = due_for(student, year)
            enrollment = Enrollment.objects.filter(student=student, year=year).first()
            paid_tuition = (
                MonthlyPayment.objects.filter(student=student, year=year).aggregate(
                    total=Sum("tuition")
                )["total"]
                or 0
            )
            registration_paid = enrollment.registration_amount if enrollment else 0

            if due is None:
                entries.append(
                    {
                        "year": year.label,
                        "year_id": year.id,
                        "available": False,
                        "enrolled": enrollment is not None,
                        "total_paid": registration_paid + paid_tuition,
                    }
                )
                continue

            total_due = due.registration + due.monthly_tuition * year.tuition_months
            total_paid = registration_paid + paid_tuition
            entries.append(
                {
                    "year": year.label,
                    "year_id": year.id,
                    "available": True,
                    "enrolled": enrollment is not None,
                    "classroom": enrollment.classroom.name if enrollment else None,
                    "total_due": total_due,
                    "total_paid": total_paid,
                    "balance": max(0, total_due - total_paid),
                    "scholarship_rate": due.scholarship_rate,
                    "is_full_scholarship": due.is_full_scholarship,
                }
            )

        return Response(
            {
                "student": {
                    "id": student.id,
                    "matricule": student.matricule,
                    "name": student.full_name,
                },
                "years": entries,
            }
        )

    @action(detail=True, methods=["get"], url_path="qr")
    def qr(self, request, pk=None):
        """QR code de l'élève, en PNG."""
        from apps.attendance.qr import student_qr_png

        student = self.get_object()
        response = student_qr_png(student)
        response["Content-Disposition"] = (
            f'inline; filename="qr-{student.matricule}.png"'
        )
        return response


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
        """Élèves en retard de paiement, tous mois échus confondus.

        Les réductions et bourses sont appliquées : sans elles, un élève boursier
        à 100 % apparaissait en tête des impayés pour une somme qu'il ne devait
        pas — et se faisait relancer par SMS.
        """
        from .fees import due_map

        year = self.current_year()
        students = list(
            Student.objects.filter(status=StudentStatus.ACTIVE).select_related("classroom")
        )
        dues = due_map(year, students)

        paid = {
            row["student"]: row["total"] or 0
            for row in MonthlyPayment.objects.filter(year=year)
            .values("student")
            .annotate(total=Sum("tuition"))
        }

        from datetime import date

        today = date.today()
        elapsed = [p for p in year.tuition_month_ends if p <= today]

        results = []
        for student in students:
            due = dues.get(student.id)
            if due is None or due.monthly_tuition == 0:
                # Pas de tarif, ou bourse totale : rien n'est exigible.
                continue
            expected = due.monthly_tuition * len(elapsed)
            settled = paid.get(student.id, 0)
            if settled < expected:
                results.append(
                    {
                        "student": student.id,
                        "matricule": student.matricule,
                        "name": student.full_name,
                        "classroom": student.classroom.name,
                        "parent_phone": student.parent_phone,
                        "due": expected,
                        "paid": settled,
                        "arrears": expected - settled,
                        "months_elapsed": len(elapsed),
                        "scholarship_rate": due.scholarship_rate,
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
