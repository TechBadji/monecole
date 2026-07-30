"""Import d'un classeur Excel de gestion."""

from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.students.models import ClassRoom, Enrollment, Level, MonthlyPayment, Student, StudentStatus

from .audit import record
from .models import AuditLog
from .views_base import TenantViewSetMixin
from .workbook_import import (
    WorkbookError,
    detect_layout,
    open_workbook,
    read_management_workbook,
    read_table,
    summarize,
)

MAX_UPLOAD_BYTES = 12 * 1024 * 1024

# Ordre pédagogique, pour créer les classes absentes au bon rang.
CLASS_ORDER = ["GARDERIE", "PS", "MS", "GS", "CI", "CP", "CE1", "CE2", "CM1", "CM2"]
PRESCHOOL = {"GARDERIE", "PS", "MS", "GS"}


class WorkbookImportView(TenantViewSetMixin, APIView):
    """Reprise d'un classeur de gestion complet.

    Ingère la structure décrite dans `docs/modele-excel.md` : élèves, inscriptions
    et mensualités des dix onglets de classe, en une passe. C'est le format dans
    lequel vivent réellement les données des écoles — leur demander de convertir
    dix onglets en CSV serait leur imposer le travail que l'outil doit faire.

    Comme l'import CSV : pré-contrôle par défaut, écriture tout ou rien.
    """

    resource = "dataimport"
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        return Response(
            {
                "accepted": [".xlsx"],
                "layouts": [
                    {
                        "key": "management",
                        "label": "Classeur de gestion",
                        "detail": "Un onglet par classe (GARDERIE à CM2), en-têtes "
                        "en ligne 8, élèves à partir de la ligne 9. Reprend les "
                        "élèves, les inscriptions et les neuf mensualités.",
                    },
                    {
                        "key": "table",
                        "label": "Tableau simple",
                        "detail": "Une feuille, une ligne d'en-tête, une ligne par "
                        "enregistrement — le modèle téléchargeable, au format Excel.",
                    },
                ],
                "notes": [
                    "La disposition est détectée automatiquement.",
                    "Les classes absentes de la base sont créées au bon rang.",
                    "Un élève déjà présent conserve son matricule.",
                    "Cantine, renforcement et uniforme mensuel ne sont pas repris : "
                    "ils sont hors chiffre d'affaires dans le classeur d'origine.",
                ],
            }
        )

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "Aucun fichier transmis."})
        if upload.size > MAX_UPLOAD_BYTES:
            raise ValidationError(
                {"file": f"Fichier trop volumineux ({upload.size // 1024} Ko, "
                         f"maximum {MAX_UPLOAD_BYTES // 1024} Ko)."}
            )

        dry_run = str(request.data.get("dry_run", "true")).lower() not in (
            "false", "0", "no",
        )

        try:
            workbook = open_workbook(upload.read())
        except WorkbookError as error:
            raise ValidationError({"file": str(error)})

        layout = detect_layout(workbook)
        year = self.current_year()

        if layout == "table":
            # Un tableau simple relève de l'import CSV : on réutilise sa chaîne
            # de traitement plutôt que d'en écrire une seconde.
            from .imports import IMPORTERS

            kind = request.data.get("kind") or "students"
            if kind not in IMPORTERS:
                raise ValidationError({"kind": f"Type inconnu : {kind}."})
            rows = read_table(workbook)
            importer, _ = IMPORTERS[kind]
            report, _ = importer(request.user.school, year, rows, dry_run=dry_run)
            return Response(
                {**report.as_dict(), "layout": "table", "applied": not dry_run,
                 "rows_read": len(rows), "year": year.label}
            )

        records, warnings = read_management_workbook(workbook, year)
        if not records:
            raise ValidationError(
                {
                    "file": "Aucun élève trouvé dans les onglets de classe. "
                    "Vérifiez que les noms commencent bien en ligne 9."
                }
            )

        overview = summarize(records)
        if dry_run:
            return Response(
                {
                    "layout": "management",
                    "applied": False,
                    "dry_run": True,
                    "ok": True,
                    "warning_count": len(warnings),
                    "warnings": warnings[:100],
                    "year": year.label,
                    **overview,
                }
            )

        result = self._apply(request, year, records)
        record(request, AuditLog.Action.CREATE, year)
        return Response(
            {
                "layout": "management",
                "applied": True,
                "ok": True,
                "warning_count": len(warnings),
                "warnings": warnings[:100],
                "year": year.label,
                **overview,
                **result,
            }
        )

    @transaction.atomic
    def _apply(self, request, year, records):
        school = request.user.school

        classrooms = {c.name.upper(): c for c in ClassRoom.objects.all()}
        for name in {record["class_name"] for record in records}:
            if name not in classrooms:
                classrooms[name] = ClassRoom.objects.create(
                    school=school,
                    name=name,
                    level=Level.PRESCHOOL if name in PRESCHOOL else Level.PRIMARY,
                    order=CLASS_ORDER.index(name) if name in CLASS_ORDER else 99,
                )

        existing = {
            (s.first_name.lower(), s.last_name.lower()): s for s in Student.objects.all()
        }

        created = updated = enrollments = payments = 0
        for entry in records:
            classroom = classrooms[entry["class_name"]]
            key = (entry["first_name"].lower(), entry["last_name"].lower())
            student = existing.get(key)

            if student is None:
                student = Student.objects.create(
                    school=school,
                    first_name=entry["first_name"],
                    last_name=entry["last_name"],
                    date_of_birth=entry["date_of_birth"],
                    classroom=classroom,
                    status=StudentStatus.ACTIVE,
                )
                existing[key] = student
                created += 1
            else:
                # Le matricule n'est jamais réattribué : il suit l'élève.
                student.classroom = classroom
                if entry["date_of_birth"]:
                    student.date_of_birth = entry["date_of_birth"]
                student.save()
                updated += 1

            if any(
                entry[field]
                for field in ("registration_amount", "uniform_amount",
                              "insurance_amount", "ape_amount")
            ) or entry["registration_paid"]:
                Enrollment.objects.update_or_create(
                    student=student,
                    year=year,
                    defaults={
                        "school": school,
                        "classroom": classroom,
                        "registration_paid": entry["registration_paid"],
                        "registration_amount": entry["registration_amount"],
                        "uniform_amount": entry["uniform_amount"],
                        "insurance_amount": entry["insurance_amount"],
                        "ape_amount": entry["ape_amount"],
                        "paid_at": year.start_date,
                    },
                )
                enrollments += 1

            for period, amount in entry["tuition"].items():
                MonthlyPayment.objects.update_or_create(
                    student=student,
                    period=period,
                    defaults={
                        "school": school,
                        "year": year,
                        "tuition": amount,
                        "payment_date": period,
                    },
                )
                payments += 1

        return {
            "created": created,
            "updated": updated,
            "enrollments": enrollments,
            "payments": payments,
        }
