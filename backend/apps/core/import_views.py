"""Endpoints d'import CSV."""

from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import record
from .imports import IMPORTERS, ImportError_, read_rows
from .models import AuditLog
from .views_base import TenantViewSetMixin

# Un CSV d'élèves d'une école de 1 000 enfants pèse moins de 200 Ko. Au-delà, il
# s'agit presque sûrement d'une erreur de fichier.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class DataImportView(TenantViewSetMixin, APIView):
    """Import CSV, en pré-contrôle puis en application.

    `POST` avec `dry_run=true` (défaut) valide et retourne le rapport sans écrire.
    Repasser `dry_run=false` applique — et n'écrit rien si une seule ligne échoue.
    """

    resource = "dataimport"
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        """Formats attendus, pour guider la préparation des fichiers."""
        return Response(
            {
                "kinds": [
                    {
                        "kind": kind,
                        "required_columns": columns["required"],
                        "optional_columns": columns.get("optional", []),
                    }
                    for kind, (_, columns) in IMPORTERS.items()
                ],
                "notes": [
                    "Séparateur point-virgule ou virgule, détecté automatiquement.",
                    "Encodages acceptés : UTF-8, UTF-8 BOM, Windows-1252, Latin-1.",
                    "Dates au format JJ/MM/AAAA ou AAAA-MM-JJ.",
                    "Montants avec ou sans séparateur de milliers : 15 000, 15.000, 15000.",
                ],
            }
        )

    def post(self, request):
        kind = request.data.get("kind")
        if kind not in IMPORTERS:
            raise ValidationError(
                {"kind": f"Type inconnu. Attendu : {', '.join(IMPORTERS)}."}
            )

        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "Aucun fichier transmis."})
        if upload.size > MAX_UPLOAD_BYTES:
            raise ValidationError(
                {"file": f"Fichier trop volumineux ({upload.size // 1024} Ko, "
                         f"maximum {MAX_UPLOAD_BYTES // 1024} Ko)."}
            )

        # `dry_run` n'est faux que sur une valeur explicite : un paramètre absent ou
        # mal orthographié ne doit jamais déclencher une écriture non voulue.
        dry_run = str(request.data.get("dry_run", "true")).lower() not in ("false", "0", "no")

        try:
            _, rows = read_rows(upload.read())
        except ImportError_ as error:
            raise ValidationError({"file": str(error)})

        importer, _ = IMPORTERS[kind]
        year = self.current_year()
        report, _ = importer(request.user.school, year, rows, dry_run=dry_run)

        if not dry_run and report.errors:
            # Rien n'a été écrit : on le dit clairement plutôt que de laisser croire
            # à un import partiel.
            return Response(
                {**report.as_dict(), "applied": False,
                 "detail": "Aucune donnée écrite : corrigez les erreurs puis relancez."},
                status=400,
            )

        if not dry_run:
            record(request, AuditLog.Action.CREATE, year)

        return Response(
            {
                **report.as_dict(),
                "applied": not dry_run,
                "rows_read": len(rows),
                "year": year.label,
            }
        )
