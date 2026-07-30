"""Matières, compositions, saisie des notes et bulletins."""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from apps.core.audit import AuditedModelViewSetMixin, record
from apps.core.models import AuditLog, Role
from apps.core.views_base import TenantModelViewSet, TenantViewSetMixin
from apps.staff.models import Teacher
from apps.students.models import ClassRoom, Student, StudentStatus

from .models import (
    ClassSubject,
    Composition,
    Grade,
    GradeSheet,
    ReportCardSettings,
    Subject,
)
from .services import class_summary, sheet_completeness, student_results


# --------------------------------------------------------------------------- #
# Sérialiseurs                                                                 #
# --------------------------------------------------------------------------- #


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "code", "name", "default_coefficient", "order", "is_active"]


class ClassSubjectSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    classroom_name = serializers.CharField(source="classroom.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True, default=None)

    class Meta:
        model = ClassSubject
        fields = [
            "id", "classroom", "classroom_name", "subject", "subject_name",
            "year", "coefficient", "teacher", "teacher_name", "order",
        ]


class CompositionSerializer(serializers.ModelSerializer):
    sheets_total = serializers.SerializerMethodField()
    sheets_validated = serializers.SerializerMethodField()

    class Meta:
        model = Composition
        fields = [
            "id", "year", "name", "kind", "term", "date", "status",
            "sheets_total", "sheets_validated", "created_at",
        ]

    def get_sheets_total(self, obj):
        return obj.sheets.count()

    def get_sheets_validated(self, obj):
        return obj.sheets.filter(is_validated=True).count()

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        term = attrs.get("term", getattr(self.instance, "term", None))
        if kind == Composition.Kind.TERM and term not in (1, 2, 3):
            raise serializers.ValidationError(
                {"term": "Une composition trimestrielle doit porter un trimestre (1, 2 ou 3)."}
            )
        return attrs


class ReportCardSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportCardSettings
        fields = [
            "id", "logo", "header_line_1", "header_line_2", "header_line_3",
            "establishment_code", "principal_name", "principal_title",
            "show_rank", "show_class_average", "footer_note",
        ]


# --------------------------------------------------------------------------- #
# Référentiels                                                                 #
# --------------------------------------------------------------------------- #


class SubjectViewSet(TenantModelViewSet):
    serializer_class = SubjectSerializer
    resource = "subject"
    model = Subject
    filterset_fields = ["is_active"]

    @action(detail=False, methods=["post"], url_path="seed-defaults")
    def seed_defaults(self, request):
        """Crée les matières usuelles de l'élémentaire sénégalais.

        Évite à chaque école de saisir huit matières à la main pour démarrer. Les
        matières déjà présentes ne sont pas dupliquées.
        """
        from .models import DEFAULT_SUBJECTS

        existing = set(Subject.objects.values_list("code", flat=True))
        created = []
        for order, (code, name, coefficient) in enumerate(DEFAULT_SUBJECTS):
            if code in existing:
                continue
            created.append(
                Subject.objects.create(
                    school=request.user.school,
                    code=code,
                    name=name,
                    default_coefficient=coefficient,
                    order=order,
                )
            )
        return Response(
            {"created": len(created), "subjects": SubjectSerializer(created, many=True).data},
            status=201,
        )


class ClassSubjectViewSet(TenantModelViewSet):
    serializer_class = ClassSubjectSerializer
    resource = "subject"
    model = ClassSubject
    select_related = ("classroom", "subject", "teacher")
    filterset_fields = ["classroom", "year", "teacher"]


class ClassSubjectBulkView(TenantViewSetMixin, APIView):
    """Affectation groupée de matières à une classe.

    L'administration configure une classe en une fois : cocher huit matières et
    poser leurs coefficients, plutôt que huit créations successives.
    """

    resource = "subject"

    def post(self, request):
        if request.user.role != Role.ADMIN:
            raise PermissionDenied("Seul un administrateur configure les matières.")

        classroom_id = request.data.get("classroom")
        year_id = request.data.get("year")
        entries = request.data.get("subjects") or []

        classroom = ClassRoom.objects.filter(pk=classroom_id).first()
        if classroom is None:
            raise NotFound("Classe introuvable.")

        from apps.core.models import SchoolYear

        year = SchoolYear.objects.filter(pk=year_id).first()
        if year is None:
            raise ValidationError({"year": "Année scolaire introuvable."})

        created, updated, removed = 0, 0, 0
        keep = set()
        with transaction.atomic():
            for order, entry in enumerate(entries):
                subject = Subject.objects.filter(pk=entry.get("subject")).first()
                if subject is None:
                    continue
                link, was_created = ClassSubject.objects.update_or_create(
                    classroom=classroom,
                    subject=subject,
                    year=year,
                    defaults={
                        "school": request.user.school,
                        "coefficient": int(entry.get("coefficient") or subject.default_coefficient),
                        "teacher_id": entry.get("teacher") or None,
                        "order": order,
                    },
                )
                keep.add(link.id)
                created += int(was_created)
                updated += int(not was_created)

            # Les matières décochées sont retirées — sauf si des notes existent
            # déjà : les supprimer effacerait le travail des enseignants.
            obsolete = ClassSubject.objects.filter(
                classroom=classroom, year=year
            ).exclude(id__in=keep)
            protected = []
            for link in obsolete:
                if link.sheets.exists():
                    protected.append(link.subject.name)
                else:
                    link.delete()
                    removed += 1

        return Response(
            {
                "created": created,
                "updated": updated,
                "removed": removed,
                "protected": protected,
                "detail": (
                    f"{', '.join(protected)} : des notes existent, la matière est "
                    f"conservée."
                    if protected
                    else None
                ),
            }
        )


class CompositionViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    serializer_class = CompositionSerializer
    resource = "composition"
    model = Composition
    select_related = ("year",)
    filterset_fields = ["year", "kind", "status", "term"]

    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        """Ouvre la saisie et crée une feuille de notes par matière de classe.

        Les feuilles sont pré-remplies avec un enregistrement par élève : sans
        cela, un élève oublié n'apparaîtrait nulle part et son absence de note
        passerait pour un choix.
        """
        composition = self.get_object()
        if composition.status == Composition.Status.CLOSED:
            raise ValidationError({"status": "Composition clôturée : réouverture refusée."})

        class_subjects = list(
            ClassSubject.objects.filter(year=composition.year).select_related("classroom")
        )
        if not class_subjects:
            raise ValidationError(
                {
                    "detail": "Aucune matière rattachée à une classe pour cette année. "
                    "Configurez les matières avant d'ouvrir la saisie."
                }
            )

        created_sheets = 0
        created_grades = 0
        with transaction.atomic():
            for class_subject in class_subjects:
                sheet, created = GradeSheet.objects.get_or_create(
                    school=request.user.school,
                    composition=composition,
                    class_subject=class_subject,
                )
                created_sheets += int(created)

                students = Student.objects.filter(
                    classroom=class_subject.classroom, status=StudentStatus.ACTIVE
                )
                known = set(
                    Grade.objects.filter(sheet=sheet).values_list("student_id", flat=True)
                )
                Grade.objects.bulk_create(
                    [
                        Grade(school=request.user.school, sheet=sheet, student=student)
                        for student in students
                        if student.id not in known
                    ]
                )
                created_grades += students.exclude(id__in=known).count()

            composition.status = Composition.Status.OPEN
            composition.save(update_fields=["status"])

        record(request, AuditLog.Action.UPDATE, composition)
        return Response(
            {
                "status": composition.status,
                "sheets_created": created_sheets,
                "grades_created": created_grades,
            }
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Clôture la composition : plus aucune note ne peut être modifiée."""
        if request.user.role != Role.ADMIN:
            raise PermissionDenied("Seul un administrateur peut clôturer une composition.")
        composition = self.get_object()
        composition.status = Composition.Status.CLOSED
        composition.save(update_fields=["status"])
        record(request, AuditLog.Action.UPDATE, composition)
        return Response({"status": composition.status})

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        """État de saisie par matière, avant édition des bulletins."""
        composition = self.get_object()
        rows = sheet_completeness(composition)
        return Response(
            {
                "composition": composition.name,
                "status": composition.status,
                "total": len(rows),
                "validated": sum(1 for r in rows if r["validated"]),
                "complete": sum(1 for r in rows if r["complete"]),
                "results": rows,
            }
        )


# --------------------------------------------------------------------------- #
# Saisie des notes                                                             #
# --------------------------------------------------------------------------- #


class GradeEntryViewSet(TenantViewSetMixin, ViewSet):
    """Saisie des notes par l'enseignant, feuille par feuille."""

    resource = "grade"

    def _teacher_of(self, user):
        """Enseignant correspondant au compte connecté.

        Le rattachement se fait par email : c'est ce que le secrétariat saisit
        déjà dans la fiche du personnel.
        """
        if not user.email:
            return None
        return Teacher.objects.filter(email__iexact=user.email, is_active=True).first()

    def _accessible_sheets(self, user):
        sheets = GradeSheet.objects.select_related(
            "composition", "class_subject__subject", "class_subject__classroom",
            "class_subject__teacher",
        )
        if user.role == Role.TEACHER:
            teacher = self._teacher_of(user)
            if teacher is None:
                return sheets.none()
            # L'enseignant ne voit que les matières qui lui sont attribuées.
            return sheets.filter(class_subject__teacher=teacher)
        return sheets

    def list(self, request):
        """Feuilles de notes accessibles à l'utilisateur."""
        composition = request.query_params.get("composition")
        sheets = self._accessible_sheets(request.user)
        if composition:
            sheets = sheets.filter(composition_id=composition)

        return Response(
            {
                "results": [
                    {
                        "id": sheet.id,
                        "composition": sheet.composition.name,
                        "composition_status": sheet.composition.status,
                        "classroom": sheet.class_subject.classroom.name,
                        "classroom_id": sheet.class_subject.classroom_id,
                        "subject": sheet.class_subject.subject.name,
                        "coefficient": sheet.class_subject.coefficient,
                        "validated": sheet.is_validated,
                        "students": sheet.grades.count(),
                        "entered": sheet.grades.exclude(
                            value__isnull=True, is_absent=False
                        ).count(),
                    }
                    for sheet in sheets.order_by(
                        "class_subject__classroom__order", "class_subject__order"
                    )
                ]
            }
        )

    def retrieve(self, request, pk=None):
        """Grille de saisie d'une feuille : un élève par ligne."""
        sheet = self._accessible_sheets(request.user).filter(pk=pk).first()
        if sheet is None:
            raise NotFound("Feuille de notes introuvable.")

        grades = sheet.grades.select_related("student").order_by(
            "student__last_name", "student__first_name"
        )
        return Response(
            {
                "id": sheet.id,
                "composition": sheet.composition.name,
                "composition_status": sheet.composition.status,
                "editable": sheet.composition.accepts_grades and not sheet.is_validated,
                "classroom": sheet.class_subject.classroom.name,
                "subject": sheet.class_subject.subject.name,
                "coefficient": sheet.class_subject.coefficient,
                "validated": sheet.is_validated,
                "validated_at": sheet.validated_at,
                "validated_by": sheet.validated_by,
                "rows": [
                    {
                        "grade": grade.id,
                        "student": grade.student_id,
                        "matricule": grade.student.matricule,
                        "name": grade.student.full_name,
                        "value": grade.value,
                        "is_absent": grade.is_absent,
                        "comment": grade.comment,
                    }
                    for grade in grades
                ],
            }
        )

    @action(detail=True, methods=["post"])
    def save(self, request, pk=None):
        """Enregistre les notes d'une feuille, en une transaction.

        Refusé si la composition n'est pas ouverte ou si la feuille est déjà
        validée : une note remise dans un bulletin distribué ne se corrige pas en
        silence, il faut d'abord dévalider.
        """
        sheet = self._accessible_sheets(request.user).filter(pk=pk).first()
        if sheet is None:
            raise NotFound("Feuille de notes introuvable.")
        if not sheet.composition.accepts_grades:
            raise ValidationError(
                {"detail": f"Saisie fermée : composition « {sheet.composition.get_status_display()} »."}
            )
        if sheet.is_validated:
            raise ValidationError(
                {"detail": "Feuille validée. Dévalidez-la avant de corriger une note."}
            )

        entries = request.data.get("rows")
        if entries is None and request.data.get("grade") is not None:
            # Saisie unitaire : la charge utile porte directement la ligne.
            entries = [request.data]
        if not isinstance(entries, list) or not entries:
            raise ValidationError({"rows": "Aucune note transmise."})

        from decimal import Decimal, InvalidOperation

        known = {g.id: g for g in sheet.grades.all()}
        updates = []
        for entry in entries:
            grade = known.get(entry.get("grade"))
            if grade is None:
                continue

            absent = bool(entry.get("is_absent"))
            raw = entry.get("value")
            value = None
            if not absent and raw not in (None, ""):
                try:
                    value = Decimal(str(raw))
                except (InvalidOperation, TypeError):
                    raise ValidationError(
                        {"rows": f"Note illisible pour {grade.student.full_name} : « {raw} »."}
                    )
                if value < 0 or value > 20:
                    raise ValidationError(
                        {
                            "rows": f"Note hors barème pour {grade.student.full_name} : "
                            f"{value}. Attendu entre 0 et 20."
                        }
                    )

            grade.value = None if absent else value
            grade.is_absent = absent
            grade.comment = entry.get("comment") or ""
            updates.append(grade)

        with transaction.atomic():
            Grade.objects.bulk_update(updates, ["value", "is_absent", "comment"])

        return Response({"saved": len(updates)})

    @action(detail=True, methods=["post"], url_path="save-one")
    def save_one(self, request, pk=None):
        """Enregistre une seule note.

        Complète la saisie par lot : l'enseignant qui corrige une copie isolée, ou
        l'administration qui rattrape un absent, n'a pas à renvoyer toute la
        classe. Même contrôle de barème que la saisie groupée — c'est le même
        code, appelé avec une seule ligne.
        """
        return self.save(request, pk)

    @action(detail=True, methods=["post"])
    def validate_sheet(self, request, pk=None):
        """L'enseignant déclare sa saisie terminée.

        Contrôle de complétude : une feuille validée avec des notes manquantes
        produirait un bulletin faux. Mieux vaut refuser et nommer les élèves
        concernés.
        """
        sheet = self._accessible_sheets(request.user).filter(pk=pk).first()
        if sheet is None:
            raise NotFound("Feuille de notes introuvable.")
        if not sheet.composition.accepts_grades:
            raise ValidationError({"detail": "Composition non ouverte à la saisie."})

        # `full_name` est une propriété, pas une colonne : on nomme les élèves
        # depuis les instances, pour que le message soit exploitable.
        incomplete = list(
            sheet.grades.filter(value__isnull=True, is_absent=False).select_related("student")
        )
        missing = [grade.student.full_name for grade in incomplete]
        if missing:
            raise ValidationError(
                {
                    "detail": f"{len(missing)} élève(s) sans note ni mention d'absence. "
                    f"Complétez ou marquez-les absents avant de valider.",
                    "missing": missing[:20],
                }
            )

        sheet.is_validated = True
        sheet.validated_at = timezone.now()
        sheet.validated_by = request.user.get_full_name() or request.user.email
        sheet.save(update_fields=["is_validated", "validated_at", "validated_by"])
        record(request, AuditLog.Action.UPDATE, sheet)
        return Response({"validated": True, "validated_at": sheet.validated_at})

    @action(detail=True, methods=["post"])
    def unvalidate(self, request, pk=None):
        """Rouvre une feuille validée. Réservé à l'administration."""
        if request.user.role not in (Role.ADMIN,):
            raise PermissionDenied("Seul un administrateur peut dévalider une feuille.")
        sheet = GradeSheet.objects.filter(pk=pk).first()
        if sheet is None:
            raise NotFound("Feuille de notes introuvable.")
        sheet.is_validated = False
        sheet.validated_at = None
        sheet.validated_by = ""
        sheet.save(update_fields=["is_validated", "validated_at", "validated_by"])
        record(request, AuditLog.Action.UPDATE, sheet)
        return Response({"validated": False})


# --------------------------------------------------------------------------- #
# Bulletins                                                                    #
# --------------------------------------------------------------------------- #


class ReportCardViewSet(TenantViewSetMixin, ViewSet):
    """Consultation et édition des bulletins."""

    resource = "reportcard"

    def _composition(self, request):
        raw = request.query_params.get("composition")
        if not raw:
            raise ValidationError({"composition": "Paramètre requis."})
        composition = Composition.objects.filter(pk=raw).first()
        if composition is None:
            raise NotFound("Composition introuvable.")
        return composition

    def _classroom(self, request):
        raw = request.query_params.get("classroom")
        if not raw:
            raise ValidationError({"classroom": "Paramètre requis."})
        classroom = ClassRoom.objects.filter(pk=raw).first()
        if classroom is None:
            raise NotFound("Classe introuvable.")
        return classroom

    def list(self, request):
        """Résultats d'une classe pour une composition, rang compris."""
        composition = self._composition(request)
        classroom = self._classroom(request)
        results, subjects, _ = student_results(composition, classroom)

        return Response(
            {
                "composition": composition.name,
                "classroom": classroom.name,
                "summary": class_summary(composition, classroom),
                "subjects": [
                    {"name": s.subject.name, "coefficient": s.coefficient} for s in subjects
                ],
                "results": sorted(
                    results.values(),
                    key=lambda r: (r["rank"] is None, r["rank"] or 0, r["name"]),
                ),
            }
        )

    @action(detail=False, methods=["get"])
    def pdf(self, request):
        """Bulletin individuel, ou tous ceux d'une classe en un seul fichier.

        `?student=<id>` produit un bulletin ; sans lui, toute la classe, un
        bulletin par page — c'est ce qui permet d'imprimer en une passe.
        """
        from .report_card import report_cards_pdf

        composition = self._composition(request)
        classroom = self._classroom(request)
        student_id = request.query_params.get("student")

        results, subjects, students = student_results(composition, classroom)
        if student_id:
            students = [s for s in students if str(s.id) == str(student_id)]
            if not students:
                raise NotFound("Élève introuvable dans cette classe.")

        if not students:
            raise ValidationError({"detail": "Aucun élève actif dans cette classe."})

        settings = ReportCardSettings.for_school(request.user.school)
        response = report_cards_pdf(
            students=students,
            results=results,
            subjects=subjects,
            composition=composition,
            classroom=classroom,
            summary=class_summary(composition, classroom),
            school=request.user.school,
            settings=settings,
        )
        name = (
            f"bulletin-{students[0].matricule}"
            if student_id
            else f"bulletins-{classroom.name}-{composition.name}"
        )
        filename = name.lower().replace(" ", "-").replace("/", "-")
        response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
        record(request, AuditLog.Action.EXPORT, composition)
        return response


class ReportCardSettingsView(TenantViewSetMixin, APIView):
    """Paramètres du bulletin : en-tête, logo, mentions."""

    resource = "reportcard"

    def get(self, request):
        settings = ReportCardSettings.for_school(request.user.school)
        return Response(ReportCardSettingsSerializer(settings, context={"request": request}).data)

    def put(self, request):
        if request.user.role != Role.ADMIN:
            raise PermissionDenied("Réservé à l'administrateur.")
        settings = ReportCardSettings.for_school(request.user.school)
        serializer = ReportCardSettingsSerializer(
            settings, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record(request, AuditLog.Action.UPDATE, settings)
        return Response(serializer.data)
